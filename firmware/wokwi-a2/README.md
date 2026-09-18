# Đề tài A2 — Khoá cửa RFID + PIN + (stub) khuôn mặt — Firmware ESP32 + Wokwi

## 1. Cách chạy trên Wokwi (bước đầu tiên, chưa cần linh kiện)

1. Vào https://wokwi.com/projects/new/esp32 → tạo project mới.
2. Dán nội dung `sketch.ino` vào tab code.
3. Mở tab **diagram.json**, thay toàn bộ bằng file `diagram.json` đính kèm
   (hoặc bấm "Import" nếu Wokwi hỏi).
4. Vào **Library Manager** (biểu tượng quyển sách bên trái) và thêm từng thư viện
   trong `libraries.txt` — hoặc copy nội dung file đó vào ô "Custom libraries.txt"
   nếu project cho phép (tab ⚙️ → Config).
5. Bấm ▶️ Start simulation.
6. Thiết bị sẽ tự nối WiFi ảo `Wokwi-GUEST` (không cần mật khẩu) và kết nối tới
   broker công khai `test.mosquitto.org` — có thể theo dõi các topic bằng MQTT
   Explorer hoặc app di động MQTT Dashboard để xem log/status thật.

> Wokwi **không mô phỏng được camera / nhận diện khuôn mặt**. Trong firmware,
> phím `D` trên bàn phím đóng vai trò "giả lập nhận diện khuôn mặt thành công"
> — dùng để bạn quay được đủ 4 kịch bản demo bắt buộc ngay trong giai đoạn
> mô phỏng, và PHẢI ghi rõ trong báo cáo đây là bước trung gian, không tính
> là sản phẩm cuối (đúng "Nguyên tắc số một" của đề bài).

## 2. Vì sao chọn kiến trúc này (khớp với `models.py` bạn đã có)

Firmware không tự quyết định thẻ/PIN nào hợp lệ — nó gửi UID/PIN lên MQTT để
backend đối chiếu, khớp đúng cách models.py đã thiết kế:

| Trong firmware | Trong `models.py` |
|---|---|
| `DEVICE_CODE` | `Device.device_code` |
| topic `.../status` (lock_state, battery_level, tamper_detected...) | `DeviceStatusLog` |
| topic `.../event` (`TAP_SUCCESS`, `TAP_FAILED`...) | `NfcLog.event_type`, `AuditLog.action` |
| topic `.../cmd` nhận `UNLOCK/LOCK/RESET/REBOOT` | `DeviceCommand.command_type` |
| topic `.../cmd/ack` (`acknowledged/failed`) | `DeviceCommand.status` |
| topic `.../card_scan` gửi UID thô | backend hash rồi so với `AccessCard.card_uid_hash` |
| topic `.../pin_attempt` | backend so với hash PIN (bảng bạn dùng để lưu PIN cần thêm nếu chưa có — xem mục 4) |
| LWT trên `.../lwt` = "offline" | dùng để cron/subscriber cập nhật `Device.status = 'offline'` |

Vì vậy khi bạn viết subscriber Django (MQTT client chạy nền, không phải view HTTP),
subscriber chỉ cần lắng nghe đúng các topic trên và ghi thẳng vào các bảng đã có,
**không cần sửa firmware nữa** khi đổi logic nghiệp vụ ở backend.

## 3. Kịch bản demo bắt buộc của đề tài A2 (đối chiếu với `sketch.ino`)

1. **Quẹt thẻ hợp lệ → cửa mở, log hiện trên web kèm ảnh**
   → `checkRfid()` gọi `doUnlock()` + `publishEvent("TAP_SUCCESS", ...)`.
2. **Quẹt thẻ lạ 3 lần → khoá tạm 60s, còi kêu, cảnh báo**
   → `checkKeypad()`/PIN sai 3 lần gọi `enterLockout()` (đã cài; với RFID bạn
   cần thêm nhánh tương tự khi backend trả về "not found" — hiện bản demo
   Wokwi luôn mở để không phụ thuộc backend, xem TODO ở bước 4).
3. **Chủ nhà cấp OTP từ xa → nhập bàn phím → mở được, hết hạn thì không mở**
   → gửi lệnh `UNLOCK` qua topic `.../cmd` từ backend (giả lập bằng cách publish
   tay một JSON `{"command_type":"UNLOCK","command_id":"1"}` lên topic đó).
4. **Nhận diện khuôn mặt → mở cửa không cần thẻ**
   → phím `D` (stub) trong giai đoạn mô phỏng; khi có phần cứng thật, thay
   bằng sự kiện MQTT `FACE_OK` do service Python (OpenCV/face_recognition) gửi.

## 4. Việc cần làm tiếp (không nằm trong file này)

- **Backend**: viết một MQTT subscriber (paho-mqtt) chạy song song với Django
  (management command hoặc service riêng) để: nhận `card_scan`/`pin_attempt`,
  so hash, publish lại `UNLOCK`/`LOCK` xuống `.../cmd`, và ghi `NfcLog`/`AuditLog`.
  Nếu `AccountBackupCode`/PIN cho cửa chưa có bảng riêng, cân nhắc thêm model
  `DoorPin` (user, pin_hash, expires_at) tương tự cách bạn đã làm với OTP.
- **Bảo mật thật (Chương 5 báo cáo)**: đổi `WiFiClient` → `WiFiClientSecure`,
  broker riêng (Mosquitto/EMQX) cổng 8883 kèm cert; thêm chống replay bằng
  `message_id` (đã có sẵn trường, cần backend kiểm tra id đã dùng chưa).
- **Chuyển sang phần cứng thật**: đúng các chân đã khai báo trong `sketch.ino`
  (đổi `WIFI_SSID/WIFI_PASS` thật, `MQTT_HOST` thật); phần cứng dùng ESP32
  DevKit V1 giống hệt Wokwi nên không cần viết lại code, chỉ cắm dây theo
  `diagram.json`.
- **Nhận diện khuôn mặt thật**: thêm ESP32-CAM (SPI/I2C riêng, không dùng
  chung ESP32 điều khiển khoá để tránh xung đột tài nguyên) chụp ảnh, gửi
  HTTPS multipart lên FastAPI/Flask chạy `face_recognition`/InsightFace,
  service này publish `{"command_type":"UNLOCK"}` lên `.../cmd` khi khớp mặt.
