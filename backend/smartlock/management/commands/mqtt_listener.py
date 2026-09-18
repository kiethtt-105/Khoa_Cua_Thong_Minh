"""
Chạy: python manage.py mqtt_listener

Đây là "tiến trình subscriber nhận dữ liệu từ MQTT" mà đề bài yêu cầu (Lớp 3 —
Backend). Nó KHÔNG phải một Django view/HTTP request — mà là một tiến trình
nền chạy riêng, giữ kết nối MQTT liên tục và ghi thẳng vào database qua ORM.

Luồng dữ liệu:
  ESP32 --publish--> broker MQTT --subscribe--> lệnh này --ORM--> DB
  lệnh này --publish UNLOCK--> broker MQTT --subscribe--> ESP32
"""
import hashlib
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

import paho.mqtt.client as mqtt

from smartlock.models import (
    Device,
    DeviceStatusLog,
    DeviceCommand,
    AccessCard,
    CardDeviceAccess,
    NfcReader,
    NfcLog,
    AuditLog,
)

PREFIX = settings.MQTT_TOPIC_PREFIX


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def topic_device_code(topic: str) -> str | None:
    # huit/iot/{device_code}/xxx
    parts = topic.split("/")
    if len(parts) >= 3:
        return parts[2]
    return None


class Command(BaseCommand):
    help = "Chạy MQTT subscriber nối firmware ESP32 với database (đề tài A2)"

    def handle(self, *args, **options):
        client = mqtt.Client(client_id="django-backend-a2")
        client.on_connect = self.on_connect
        client.on_message = self.on_message

        self.stdout.write(f"Đang kết nối MQTT broker {settings.MQTT_HOST}:{settings.MQTT_PORT} ...")
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
        client.loop_forever()

    # ---------------- MQTT callbacks ----------------
    def on_connect(self, client, userdata, flags, rc):
        self.stdout.write(self.style.SUCCESS(f"Đã kết nối MQTT (rc={rc})"))
        subs = ["card_scan", "pin_attempt", "event", "status", "lwt", "cmd/ack"]
        for s in subs:
            topic = f"{PREFIX}/+/{s}"
            client.subscribe(topic)
            self.stdout.write(f"  subscribe: {topic}")
        self._client = client

    def on_message(self, client, userdata, msg):
        try:
            device_code = topic_device_code(msg.topic)
            if not device_code:
                return
            suffix = msg.topic.rsplit("/", 1)[-1]

            if msg.topic.endswith("/lwt"):
                self.handle_lwt(device_code, msg.payload.decode())
            elif suffix == "scan" or msg.topic.endswith("/card_scan"):
                self.handle_card_scan(device_code, msg.payload)
            elif msg.topic.endswith("/pin_attempt"):
                self.handle_pin_attempt(device_code, msg.payload)
            elif msg.topic.endswith("/event"):
                self.handle_event(device_code, msg.payload)
            elif msg.topic.endswith("/status"):
                self.handle_status(device_code, msg.payload)
            elif msg.topic.endswith("/cmd/ack"):
                self.handle_ack(device_code, msg.payload)
        except Exception as exc:  # không được để 1 message lỗi làm chết cả subscriber
            self.stderr.write(self.style.ERROR(f"Lỗi xử lý {msg.topic}: {exc}"))

    # ---------------- Xử lý nghiệp vụ ----------------
    def get_device(self, device_code: str) -> Device | None:
        return Device.objects.filter(device_code=device_code).first()

    def handle_lwt(self, device_code, payload):
        device = self.get_device(device_code)
        if not device:
            return
        device.status = "offline" if payload == "offline" else "online"
        device.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            device=device,
            action="READER_DISCONNECTED" if payload == "offline" else "READER_CONNECTED",
            success=True,
        )

    def handle_status(self, device_code, raw_payload):
        device = self.get_device(device_code)
        if not device:
            self.stdout.write(f"[status] Chưa có Device với device_code={device_code}, bỏ qua")
            return
        data = json.loads(raw_payload)
        device.status = "online"
        device.battery_level = data.get("battery_level", device.battery_level)
        device.last_seen_at = timezone.now()
        device.save(update_fields=["status", "battery_level", "last_seen_at", "updated_at"])

        DeviceStatusLog.objects.create(
            device=device,
            battery_level=data.get("battery_level", 0),
            signal_strength=data.get("signal_strength"),
            lock_state=data.get("lock_state", "unknown"),
            tamper_detected=data.get("tamper_detected", False),
            raw_payload=data,
        )

    def handle_card_scan(self, device_code, raw_payload):
        device = self.get_device(device_code)
        data = json.loads(raw_payload)
        uid = data.get("card_uid", "")
        uid_hash = sha256_hex(uid)

        card = AccessCard.objects.filter(card_uid_hash=uid_hash, is_active=True).first()
        allowed = False
        if card and device:
            allowed = CardDeviceAccess.objects.filter(
                access_card=card, device=device, is_active=True
            ).exists()

        NfcLog.objects.create(
            device=device,
            nfc_tag=card,
            user=card.user if card else None,
            event_type="TAP_SUCCESS" if allowed else "TAP_FAILED",
            success=allowed,
            metadata={"uid_hash_prefix": uid_hash[:8]},  # không log UID/hash đầy đủ vào log thường
        )

        if allowed and device:
            self.send_unlock_command(device, issued_by=card.user)

    def handle_pin_attempt(self, device_code, raw_payload):
        # GHI CHÚ: firmware hiện tại (bản Wokwi demo) CHỦ Ý không gửi PIN dạng
        # thô lên topic này (chỉ gửi pin_length) để tránh lộ PIN trên broker
        # công khai test.mosquitto.org. Khi đã bật TLS + broker riêng, sửa
        # firmware gửi kèm PIN thật, rồi bổ sung logic so sánh với
        # DoorPinCode.pin_hash tại đây (dùng cùng cách băm PBKDF2/argon2 như
        # các trường *_hash khác trong models.py).
        device = self.get_device(device_code)
        data = json.loads(raw_payload)
        AuditLog.objects.create(
            device=device,
            action="TAP_FAILED",
            success=False,
            metadata={"note": "pin_attempt nhận được nhưng chưa bật xác thực PIN qua TLS", **data},
        )

    def handle_event(self, device_code, raw_payload):
        device = self.get_device(device_code)
        data = json.loads(raw_payload)
        event_type = data.get("event_type", "OTHER")
        NfcLog.objects.create(
            device=device,
            event_type=event_type if event_type in dict(NfcLog._meta.get_field("event_type").choices) else "TAP_FAILED",
            success=data.get("success", False),
            metadata=data,
        )

    def handle_ack(self, device_code, raw_payload):
        data = json.loads(raw_payload)
        command_id = data.get("command_id")
        status = data.get("status")
        if not command_id:
            return
        DeviceCommand.objects.filter(id=command_id).update(
            status=status,
            acknowledged_at=timezone.now() if status == "acknowledged" else None,
        )

    def send_unlock_command(self, device: Device, issued_by=None):
        command = DeviceCommand.objects.create(
            device=device,
            issued_by=issued_by or device.owner,
            command_type="UNLOCK",
            status="sent",
            command_token_hash=sha256_hex(f"{device.id}-{timezone.now().isoformat()}"),
            expires_at=timezone.now() + timezone.timedelta(seconds=30),
        )
        topic = f"{PREFIX}/{device.device_code}/cmd"
        payload = json.dumps({
            "command_type": "UNLOCK",
            "command_id": str(command.id),
        })
        self._client.publish(topic, payload)
        self.stdout.write(f"-> Đã gửi UNLOCK cho {device.device_code} (command_id={command.id})")
