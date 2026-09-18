# smartlock/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
import uuid

from .models import (
    User, Device, AccessCard, ShareAccessCode, SupportRequest, Notification,
    AuditLog, DeviceAccess, SystemSettings, EmailVerificationToken
)
from .email_templates import render_email

@login_required
def dashboard(request):
    """Dashboard chính (tổng quan)"""
    context = {
        'user': request.user,
        'total_devices': Device.objects.filter(owner=request.user).count(),
        'online_devices': Device.objects.filter(owner=request.user, status='online').count(),
        'unapproved_cards': AccessCard.objects.filter(user=request.user, is_active=False).count(),
        'recent_logs': AuditLog.objects.filter(actor_user=request.user).order_by('-created_at')[:5],
    }
    return render(request, 'account/base/dashboard.html', context)

@login_required
def login_view(request):
    """Đăng nhập"""
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            messages.success(request, 'Đăng nhập thành công!')
            return redirect('account:dashboard')
        else:
            messages.error(request, 'Email hoặc mật khẩu không đúng.')
    return render(request, 'account/base/login.html')

@login_required
def logout_view(request):
    """Đăng xuất"""
    logout(request)
    return redirect('account:login')

@login_required
def register(request):
    """Đăng ký tài khoản"""
    if request.method == 'POST':
        # logic tạo user + gửi email xác thực
        email = request.POST.get('email')
        username = request.POST.get('username')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        full_name = request.POST.get('full_name')

        if password1 != password2:
            messages.error(request, 'Mật khẩu không khớp.')
            return render(request, 'account/base/register.html')

        user = User.objects.create_user(email=email, username=username, password=password1)
        user.full_name = full_name
        user.save()

        # Tạo token xác thực
        token = uuid.uuid4()
        EmailVerificationToken.objects.create(
            user=user,
            purpose='EMAIL_VERIFY',
            token_hash=token,
            expires_at=timezone.now() + timezone.timedelta(minutes=30)
        )

        # Gửi email
        context = {
            'full_name': full_name or username,
            'verification_link': f"{request.build_absolute_uri('/verify-email/')}{token}/",
        }
        subject, html, plain = render_email('user_verification.html', context)
        send_mail(subject, plain, 'no-reply@smartlock.com', [email])

        messages.success(request, 'Đăng ký thành công! Vui lòng kiểm tra email.')
        return redirect('account:login')
    return render(request, 'account/base/register.html')

@login_required
def verify_email(request, token):
    """Xác thực email"""
    try:
        vt = EmailVerificationToken.objects.get(token_hash=token, is_used=False)
        vt.user.email_verified = True
        vt.user.is_active = True
        vt.user.save()
        vt.is_used = True
        vt.save()
        messages.success(request, 'Tài khoản đã được kích hoạt thành công!')
    except:
        messages.error(request, 'Link xác thực không hợp lệ.')
    return redirect('account:login')

# ====================== DEVICE VIEWS ======================
@login_required
def devices_list(request):
    """Danh sách thiết bị của user"""
    devices = Device.objects.filter(owner=request.user)
    return render(request, 'account/devices/list.html', {'device_list': devices})

@login_required
def device_detail(request, device_id):
    """Chi tiết thiết bị"""
    device = get_object_or_404(Device, id=device_id, owner=request.user)
    return render(request, 'account/devices/detail.html', {'device': device})

# ====================== NFC VIEWS ======================
@login_required
def nfc_tags(request):
    """Quản lý thẻ NFC"""
    cards = AccessCard.objects.filter(user=request.user)
    return render(request, 'account/nfc/tags.html', {'access_cards': cards})

@login_required
def nfc_reader(request):
    """Đọc thẻ NFC (demo)"""
    return render(request, 'account/nfc/reader.html')

# ====================== SHARE & SUPPORT ======================
@login_required
def share_codes(request):
    """Mã chia sẻ"""
    codes = ShareAccessCode.objects.filter(device__owner=request.user)
    return render(request, 'account/share/codes.html', {'share_codes': codes})

@login_required
def share_request(request):
    """Yêu cầu chia sẻ"""
    return render(request, 'account/share/request.html')

@login_required
def support_requests(request):
    """Yêu cầu hỗ trợ"""
    requests = SupportRequest.objects.filter(requested_by=request.user)
    return render(request, 'account/support/requests.html', {'support_requests': requests})

@login_required
def support_request_detail(request, request_id):
    """Chi tiết yêu cầu hỗ trợ"""
    req = get_object_or_404(SupportRequest, id=request_id, requested_by=request.user)
    return render(request, 'account/support/request_detail.html', {'request': req})

# ====================== ADMIN / SETTINGS ======================
@login_required
def permissions_manage(request):
    """Quyền hạn"""
    return render(request, 'account/permissions/manage.html')

@login_required
def settings_system(request):
    """Cài đặt hệ thống"""
    settings = SystemSettings.objects.first()
    return render(request, 'account/settings/system.html', {'settings': settings})

@login_required
def notifications_list(request):
    """Thông báo"""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'account/base/notifications.html', {'notifications': notifications})

@login_required
def profile(request):
    """Thông tin tài khoản"""
    return render(request, 'account/base/profile.html', {'user': request.user})

@login_required
def audit_logs(request):
    """Nhật ký hệ thống"""
    logs = AuditLog.objects.filter(actor_user=request.user).order_by('-created_at')
    return render(request, 'account/audit/logs.html', {'audit_logs': logs})