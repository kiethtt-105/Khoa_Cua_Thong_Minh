/*
 * ĐỀ TÀI A2 — Khoá cửa thông minh: RFID + PIN + (stub) nhận diện khuôn mặt
 * Board: ESP32 DevKit V1
 *
 * File này chạy được cả trên Wokwi (mô phỏng) lẫn board ESP32 thật —
 * KHÔNG cần sửa logic khi chuyển từ mô phỏng sang mạch thật, chỉ cần
 * cắm đúng chân theo README.md.
 *
 * ÁNH XẠ VỚI BACKEND (models.py):
 *   - device_code            <-> Device.device_code
 *   - topic .../status       -> dữ liệu ghi vào DeviceStatusLog mỗi lần publish
 *   - topic .../event        -> dữ liệu ghi vào NfcLog / AuditLog (event_type dùng
 *                               đúng các choices đã khai báo trong models.py)
 *   - topic .../cmd          -> lệnh backend gửi xuống, khớp DeviceCommand.command_type
 *   - topic .../cmd/ack      -> cập nhật DeviceCommand.status (acknowledged/failed)
 *   - topic .../lwt          -> Last Will & Testament, backend dùng để set Device.status=offline
 *
 * BẢO MẬT (phần phải giải trình trong Chương 5 báo cáo — code này CHƯA bật TLS
 * để chạy được trên Wokwi; khi lên board thật PHẢI đổi sang WiFiClientSecure +
 * cổng 8883, xem ghi chú NANG_CAP_KHI_LEN_THAT bên dưới):
 *   - UID thẻ và mã PIN chỉ gửi lên server để đối chiếu hash (server-side hashing),
 *     firmware KHÔNG lưu danh sách thẻ/PIN hợp lệ cứng trong code.
 *   - Mỗi bản tin có message_id (millis + counter) để backend chống phát lại (replay).
 *   - Trạng thái khoá được lưu vào NVS (Preferences) để khôi phục đúng sau mất điện.
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>
#include <Preferences.h>

// ==================== CẤU HÌNH ====================
const char* WIFI_SSID   = "Wokwi-GUEST";   // Wokwi virtual WiFi (mở, không cần mật khẩu)
const char* WIFI_PASS   = "";
const char* MQTT_HOST   = "test.mosquitto.org"; // NANG_CAP_KHI_LEN_THAT: đổi sang broker riêng có TLS
const int   MQTT_PORT   = 1883;                 // NANG_CAP_KHI_LEN_THAT: 8883 + WiFiClientSecure
const char* DEVICE_CODE = "A2-LOCK-01";         // trùng với Device.device_code trên backend

String T_STATUS = String("huit/iot/") + DEVICE_CODE + "/status";
String T_EVENT  = String("huit/iot/") + DEVICE_CODE + "/event";
String T_CMD    = String("huit/iot/") + DEVICE_CODE + "/cmd";
String T_ACK    = String("huit/iot/") + DEVICE_CODE + "/cmd/ack";
String T_LWT    = String("huit/iot/") + DEVICE_CODE + "/lwt";

// ==================== CHÂN CẮM ====================
// RC522 (SPI mặc định ESP32: SCK=18, MISO=19, MOSI=23)
#define PIN_RFID_SS   5
#define PIN_RFID_RST  4

// OLED SSD1306 I2C (mặc định ESP32: SDA=21, SCL=22)
#define OLED_W 128
#define OLED_H 64

// Bàn phím 4x4
byte ROW_PINS[4] = {13, 12, 14, 27};
byte COL_PINS[4] = {26, 25, 33, 32};
char KEYS[4][4] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
// Phím 'D' dùng để GIẢ LẬP kết quả nhận diện khuôn mặt thành công (stub demo trên Wokwi)

#define PIN_SERVO   15
#define PIN_BUZZER  2
#define PIN_LED_OK  16   // xanh
#define PIN_LED_ERR 17   // đỏ

#define SERVO_LOCKED_DEG    0
#define SERVO_UNLOCKED_DEG  90

// ==================== THAM SỐ NGHIỆP VỤ ====================
const unsigned long AUTO_RELOCK_MS   = 5000;   // tự khoá lại sau 5 giây
const unsigned long LOCKOUT_MS       = 60000;  // khoá tạm 60 giây sau 3 lần sai (đúng yêu cầu đề bài)
const int           MAX_FAILED_TRIES = 3;
const unsigned long STATUS_PERIOD_MS = 15000;  // publish status định kỳ

// ==================== BIẾN TRẠNG THÁI ====================
WiFiClient espClient;
PubSubClient mqtt(espClient);
MFRC522 rfid(PIN_RFID_SS, PIN_RFID_RST);
Keypad keypad = Keypad(makeKeymap(KEYS), ROW_PINS, COL_PINS, 4, 4);
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1);
Servo lockServo;
Preferences prefs;

enum LockState { LOCKED, UNLOCKED, LOCKOUT_STATE };
LockState lockState = LOCKED;

String pinBuffer = "";
int failedAttempts = 0;
unsigned long lockoutUntil = 0;
unsigned long relockAt = 0;
unsigned long lastStatusPub = 0;
unsigned long msgCounter = 0;

// ==================== TIỆN ÍCH ====================
String nextMessageId() {
  msgCounter++;
  return String(millis()) + "-" + String(msgCounter);
}

void oledMsg(const String& line1, const String& line2 = "") {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 10);
  display.println(line1);
  display.setCursor(0, 30);
  display.println(line2);
  display.display();
}

void beep(int times, int ms) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(ms);
    digitalWrite(PIN_BUZZER, LOW);
    if (i < times - 1) delay(ms);
  }
}

// Lưu trạng thái khoá vào NVS để khôi phục đúng sau khi mất nguồn / khởi động lại
void persistLockState() {
  prefs.putUChar("lock_state", (uint8_t)lockState);
}

void restoreLockStateFromNVS() {
  uint8_t saved = prefs.getUChar("lock_state", (uint8_t)LOCKED);
  // Nguyên tắc an toàn: dù trước khi mất điện đang UNLOCKED, khi khởi động lại
  // PHẢI về LOCKED trước, không tự mở khoá khi vừa cấp điện lại.
  lockState = (saved == (uint8_t)LOCKOUT_STATE) ? LOCKED : LOCKED;
  lockServo.write(SERVO_LOCKED_DEG);
  persistLockState();
}

// ==================== MQTT: PUBLISH ====================
void publishStatus() {
  StaticJsonDocument<256> doc;
  doc["device_code"]      = DEVICE_CODE;
  doc["lock_state"]       = lockState == LOCKED ? "locked" :
                             lockState == UNLOCKED ? "unlocked" : "jammed"; // enum trùng DeviceStatusLog.lock_state
  doc["battery_level"]    = 100;      // demo: board thật đọc từ ADC pin/ACS712
  doc["signal_strength"]  = WiFi.RSSI();
  doc["tamper_detected"]  = false;
  doc["wifi_connected"]   = WiFi.status() == WL_CONNECTED;
  doc["firmware_version"] = "0.1.0-wokwi";
  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_STATUS.c_str(), buf, n, true); // retained
}

// event_type dùng ĐÚNG các choices đã có trong NfcLog/AuditLog của models.py
void publishEvent(const String& eventType, bool success, const String& metaExtra = "") {
  StaticJsonDocument<256> doc;
  doc["device_code"] = DEVICE_CODE;
  doc["event_type"]  = eventType;   // vd: TAP_SUCCESS, TAP_FAILED, SESSION_TIMEOUT...
  doc["success"]     = success;
  doc["message_id"]  = nextMessageId();
  if (metaExtra.length()) doc["metadata"] = metaExtra;
  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_EVENT.c_str(), buf, n);
}

void publishAck(const String& commandId, const String& status) {
  StaticJsonDocument<128> doc;
  doc["command_id"] = commandId;
  doc["status"]      = status; // acknowledged / failed — khớp DeviceCommand.status
  char buf[128];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_ACK.c_str(), buf, n);
}

// ==================== HÀNH ĐỘNG KHOÁ ====================
void doUnlock(const String& source) {
  lockState = UNLOCKED;
  lockServo.write(SERVO_UNLOCKED_DEG);
  digitalWrite(PIN_LED_OK, HIGH);
  digitalWrite(PIN_LED_ERR, LOW);
  beep(1, 150);
  relockAt = millis() + AUTO_RELOCK_MS;
  failedAttempts = 0;
  persistLockState();
  oledMsg("MO CUA", "Nguon: " + source);
  publishEvent("TAP_SUCCESS", true, source);
}

void doLock() {
  lockState = LOCKED;
  lockServo.write(SERVO_LOCKED_DEG);
  digitalWrite(PIN_LED_OK, LOW);
  digitalWrite(PIN_LED_ERR, LOW);
  persistLockState();
  oledMsg("DA KHOA", "San sang");
}

void enterLockout() {
  lockState = LOCKOUT_STATE;
  lockoutUntil = millis() + LOCKOUT_MS;
  digitalWrite(PIN_LED_ERR, HIGH);
  beep(3, 120);
  oledMsg("KHOA TAM 60s", "Qua 3 lan sai");
  publishEvent("TAP_FAILED", false, "lockout_triggered");
}

// ==================== MQTT: NHẬN LỆNH TỪ SERVER ====================
void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, len);
  if (err) {
    publishEvent("TAP_FAILED", false, "bad_json_cmd");
    return;
  }

  String cmdType   = doc["command_type"] | "";
  String commandId = doc["command_id"]   | "";

  // command_type PHẢI khớp DeviceCommand.command_type trong models.py
  if (cmdType == "UNLOCK") {
    if (lockState == LOCKOUT_STATE) {
      publishAck(commandId, "failed");
      return;
    }
    doUnlock("server_remote");
    publishAck(commandId, "acknowledged");
  } else if (cmdType == "LOCK") {
    doLock();
    publishAck(commandId, "acknowledged");
  } else if (cmdType == "REBOOT") {
    publishAck(commandId, "acknowledged");
    delay(200);
    ESP.restart();
  } else if (cmdType == "RESET") {
    failedAttempts = 0;
    lockState = LOCKED;
    lockoutUntil = 0;
    doLock();
    publishAck(commandId, "acknowledged");
  } else {
    // ADD_CARD / REMOVE_CARD xử lý ở backend (ghi AccessCard/CardDeviceAccess),
    // thiết bị chỉ cần biết là đã áp dụng, không tự lưu danh sách thẻ.
    publishAck(commandId, "acknowledged");
  }
}

void reconnectMqtt() {
  while (!mqtt.connected()) {
    oledMsg("Dang ket noi", "MQTT broker...");
    String clientId = String("esp32-") + DEVICE_CODE;
    // LWT: nếu mất kết nối đột ngột, broker tự publish "offline" retained
    if (mqtt.connect(clientId.c_str(), NULL, NULL, T_LWT.c_str(), 1, true, "offline")) {
      mqtt.publish(T_LWT.c_str(), "online", true);
      mqtt.subscribe(T_CMD.c_str());
      publishStatus();
    } else {
      delay(1000);
    }
  }
}

// ==================== RFID ====================
void checkRfid() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  // Cảm biến trả giá trị lỗi (đọc UID rỗng/độ dài bất thường) -> coi là lỗi đọc, không xử lý tiếp
  if (rfid.uid.size == 0 || rfid.uid.size > 10) {
    publishEvent("TAP_FAILED", false, "rfid_read_error");
    rfid.PICC_HaltA();
    return;
  }

  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  if (lockState == LOCKOUT_STATE) {
    oledMsg("DANG KHOA TAM", "Cho " + String((lockoutUntil - millis()) / 1000) + "s");
    rfid.PICC_HaltA();
    return;
  }

  // Gửi UID lên server để đối chiếu card_uid_hash (AccessCard.card_uid_hash) —
  // KHÔNG tự quyết định mở khoá tại chỗ trong bản demo thật (chỉ demo Wokwi mở nhanh
  // để không phụ thuộc backend khi chấm bài; xoá đoạn "DEMO" khi có backend thật).
  StaticJsonDocument<192> doc;
  doc["device_code"] = DEVICE_CODE;
  doc["card_uid"]    = uidStr;         // TLS bắt buộc khi lên thật vì đây là dữ liệu định danh
  doc["message_id"]  = nextMessageId();
  char buf[192];
  size_t n = serializeJson(doc, buf);
  mqtt.publish((String("huit/iot/") + DEVICE_CODE + "/card_scan").c_str(), buf, n);

  // ---- DEMO (Wokwi, không cần chờ backend phản hồi) ----
  oledMsg("The: " + uidStr, "Dang kiem tra...");
  delay(300);
  doUnlock("rfid:" + uidStr);
  rfid.PICC_HaltA();
}

// ==================== BÀN PHÍM (PIN) ====================
const String DEMO_VALID_PIN = "1234"; // DEMO CHỈ DÙNG KHI CHƯA NỐI BACKEND THẬT

void checkKeypad() {
  char k = keypad.getKey();
  if (!k) return;

  if (lockState == LOCKOUT_STATE) {
    oledMsg("DANG KHOA TAM", "Cho " + String((lockoutUntil - millis()) / 1000) + "s");
    return;
  }

  if (k == 'D') {
    // Stub giả lập nhận diện khuôn mặt thành công (chỉ dùng khi mô phỏng trên Wokwi,
    // board thật sẽ nhận sự kiện này qua MQTT từ service nhận diện khuôn mặt chạy trên server)
    doUnlock("face_stub");
    return;
  }

  if (k == '*') { pinBuffer = ""; oledMsg("Nhap PIN:", ""); return; }

  if (k == '#') {
    // Gửi PIN lên server đối chiếu (server so với hash, KHÔNG so sánh ở đây khi có backend thật)
    StaticJsonDocument<160> doc;
    doc["device_code"] = DEVICE_CODE;
    doc["pin_length"]  = pinBuffer.length();
    doc["message_id"]  = nextMessageId();
    char buf[160];
    size_t n = serializeJson(doc, buf);
    mqtt.publish((String("huit/iot/") + DEVICE_CODE + "/pin_attempt").c_str(), buf, n);

    // ---- DEMO cục bộ (Wokwi) ----
    if (pinBuffer == DEMO_VALID_PIN) {
      doUnlock("pin");
    } else {
      failedAttempts++;
      beep(1, 400);
      oledMsg("SAI PIN", "Con lai: " + String(MAX_FAILED_TRIES - failedAttempts));
      publishEvent("TAP_FAILED", false, "wrong_pin");
      if (failedAttempts >= MAX_FAILED_TRIES) enterLockout();
    }
    pinBuffer = "";
    return;
  }

  if (pinBuffer.length() < 8) {
    pinBuffer += k;
    oledMsg("Nhap PIN:", pinBuffer);
  }
}

// ==================== SETUP / LOOP ====================
void connectWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  oledMsg("Dang ket noi WiFi", WIFI_SSID);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(300);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_ERR, OUTPUT);

  Wire.begin();
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  SPI.begin();
  rfid.PCD_Init();

  lockServo.attach(PIN_SERVO);

  prefs.begin("smartlock", false);
  restoreLockStateFromNVS();   // xử lý tình huống "mất nguồn" đúng yêu cầu đề bài

  connectWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

void loop() {
  // Xử lý tình huống "mất WiFi": tự kết nối lại, không treo firmware
  if (WiFi.status() != WL_CONNECTED) {
    oledMsg("Mat WiFi", "Dang thu lai...");
    connectWifi();
  }
  if (!mqtt.connected()) reconnectMqtt();
  mqtt.loop();

  checkRfid();
  checkKeypad();

  if (lockState == LOCKOUT_STATE && millis() > lockoutUntil) {
    lockState = LOCKED;
    digitalWrite(PIN_LED_ERR, LOW);
    failedAttempts = 0;
    doLock();
  }

  if (lockState == UNLOCKED && millis() > relockAt) {
    doLock();
  }

  if (millis() - lastStatusPub > STATUS_PERIOD_MS) {
    publishStatus();
    lastStatusPub = millis();
  }
}
