# Khoa_Cua_Thong_Minh — Đề tài A2 (IoT, HUIT)

Cấu trúc thư mục:

```
Khoa_Cua_Thong_Minh/
├── backend/                  # Django backend (dùng models.py bạn đã có)
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── smartlock_backend/    # settings, urls
│   └── smartlock/            # app: models.py + mqtt_listener
├── firmware/wokwi-a2/         # firmware ESP32 + sơ đồ Wokwi
├── docker-compose.yml         # MQTT broker riêng (tuỳ chọn, dùng sau)
├── mosquitto/                 # config cho broker riêng
└── README.md                  # file này
```

Chạy đủ hệ thống cần **3 cửa sổ terminal chạy song song**: (1) Django server,
(2) MQTT subscriber, (3) mô phỏng Wokwi mở trên trình duyệt.

## Bước 0 — Yêu cầu cài sẵn

- Python 3.11+ (kiểm tra: `python --version`)
- Git

## Bước 1 — Copy code vào đúng repo Git của bạn

Bạn đang có repo trống tại `D:\.GitHub\Khoa_Cua_Thong_Minh`. Chép toàn bộ nội
dung trong file zip đính kèm vào đúng thư mục đó (đè lên `.gitattributes` cũ
không sao, giữ nguyên file đó).

## Bước 2 — Cài đặt backend (PowerShell)

```powershell
cd D:\.GitHub\Khoa_Cua_Thong_Minh\backend

# Tạo và kích hoạt virtualenv
python -m venv venv
venv\Scripts\activate

# Cài thư viện
pip install -r requirements.txt

# Tạo file .env thật từ mẫu
copy .env.example .env
```

Mở file `.env` vừa tạo, sinh FERNET_KEY bằng lệnh sau rồi dán vào dòng
`FERNET_KEY=`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Bước 3 — Khởi tạo database và chạy server

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Mở http://127.0.0.1:8000/admin/ để đăng nhập bằng superuser vừa tạo. Vào đây
tạo thử:
1. Một **Device** với `device_code = A2-LOCK-01` (đúng giá trị đang khai báo
   trong `firmware/wokwi-a2/sketch.ino`), `status = online`.
2. Một **AccessCard** với `card_uid_hash` = SHA-256 của UID thẻ RFID sẽ quẹt
   trên Wokwi (bạn xem UID hiện trên OLED khi quẹt thẻ ảo trong Wokwi, rồi tự
   băm bằng `python -c "import hashlib; print(hashlib.sha256(b'UID_CUA_BAN').hexdigest())"`).
3. Một **CardDeviceAccess** nối thẻ đó với device ở trên, `is_active = True`.

## Bước 4 — Chạy MQTT subscriber (terminal thứ 2)

```powershell
cd D:\.GitHub\Khoa_Cua_Thong_Minh\backend
venv\Scripts\activate
python manage.py mqtt_listener
```

Terminal này phải luôn mở khi demo — đây chính là "tiến trình subscriber" mà
đề bài yêu cầu (Lớp 3). Nó sẽ tự in log khi nhận được sự kiện quẹt thẻ, trạng
thái thiết bị, v.v.

## Bước 5 — Chạy mô phỏng Wokwi (terminal/tab trình duyệt thứ 3)

Theo đúng `firmware/wokwi-a2/README.md` đã có: dán `sketch.ino` +
`diagram.json` vào project Wokwi, thêm thư viện trong `libraries.txt`, bấm
Start simulation. Vì cả firmware và `backend/.env` mặc định đều trỏ về broker
công khai `test.mosquitto.org`, hai bên sẽ tự thấy nhau — không cần cấu hình
mạng gì thêm ở bước mô phỏng này.

## Kiểm tra đã chạy đúng chưa

- Quẹt thẻ RFID ảo trên Wokwi có UID đã đăng ký ở Bước 3 → terminal
  `mqtt_listener` in ra dòng `-> Đã gửi UNLOCK cho A2-LOCK-01 ...` → servo
  trên Wokwi quay mở khoá.
- Quẹt thẻ chưa đăng ký → không có dòng UNLOCK, và trong admin Django vào
  bảng `NfcLog` thấy bản ghi `TAP_FAILED`.
- Vào admin → `DeviceStatusLog` thấy log trạng thái được ghi mỗi ~15 giây.

## Vì sao chưa gọi là "sản phẩm chạy thật"

Đây vẫn là giai đoạn mô phỏng (Wokwi + broker công khai, chưa TLS, PIN chưa
verify được vì lý do bảo mật đã ghi chú trong `mqtt_listener.py`). Theo đúng
"Nguyên tắc số một" của đề bài, khi viết báo cáo phải ghi rõ đây là bước
thiết kế trung gian. Xem mục 4 trong `firmware/wokwi-a2/README.md` để biết
việc cần làm khi chuyển sang mạch thật (ESP32 thật, TLS, ESP32-CAM nhận diện
khuôn mặt).
