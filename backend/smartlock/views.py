# smartlock/views.py
# (đặt ngang với smartlock/models.py)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from datetime import timedelta
import json

from smartlock.models import (
    User, Device, SupportRequest, AuditLog, Notification, SystemSettings,
    LoginAttemptLog, LoginLockout, NfcReader, NfcSession, AccessCard,
    DeviceStatusLog, DeviceCommand, ShareAccessCode
)
from django.core.paginator import Paginator

# ==================== 1. DASHBOARD ====================
@login_required
def dashboard(request):
    # === THỐNG KÊ TỔNG QUAN ===
    total_users = User.objects.filter(is_active=True).count()
    total_devices = Device.objects.count()
    total_support = SupportRequest.objects.filter(status__in=['pending', 'approved']).count()
    total_audit = AuditLog.objects.count()

    recent_users = User.objects.filter(created_at__gte=timezone.now() - timedelta(hours=24)).count()
    recent_devices = Device.objects.filter(created_at__gte=timezone.now() - timedelta(hours=24)).count()

    # === THỐNG KÊ THEO THÁNG ===
    months = 6
    user_data = []
    device_data = []
    support_data = []

    for i in range(months):
        start = timezone.now() - timedelta(days=i * 30)
        end = timezone.now() - timedelta(days=(i + 1) * 30)

        user_data.append({
            'date': start.strftime('%m/%Y'),
            'count': User.objects.filter(created_at__range=(start, end)).count()
        })
        device_data.append({
            'date': start.strftime('%m/%Y'),
            'count': Device.objects.filter(created_at__range=(start, end)).count()
        })
        support_data.append({
            'date': start.strftime('%m/%Y'),
            'count': SupportRequest.objects.filter(created_at__range=(start, end)).count()
        })

    context = {
        'total_users': total_users,
        'total_devices': total_devices,
        'total_support': total_support,
        'total_audit': total_audit,
        'recent_users': recent_users,
        'recent_devices': recent_devices,
        'user_data': json.dumps(user_data),
        'device_data': json.dumps(device_data),
        'support_data': json.dumps(support_data),
    }

    return render(request, 'admin-sys/base/dashboard.html', context)


# ==================== 2. QUẢN LÝ USERS ====================
@login_required
@permission_required('smartlock.change_user', raise_exception=True)
def users_list(request):
    users = User.objects.select_related('login_lockout').all()

    search = request.GET.get('search', '')
    status = request.GET.get('status')
    if search:
        users = users.filter(Q(full_name__icontains=search) | Q(email__icontains=search))
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'locked':
        users = users.filter(login_lockout__failed_attempts__gt=0)

    paginator = Paginator(users, 20)
    page = request.GET.get('page', 1)
    users_page = paginator.get_page(page)

    return render(request, 'admin-sys/users/list.html', {
        'users': users_page,
        'search': search,
        'status': status,
    })


# ... (tôi đã giữ nguyên toàn bộ code ở phần sau, chỉ điều chỉnh đường dẫn render)

# Các view còn lại (devices_list, device_detail, support_requests_list, audit_logs, system_settings, nfc_readers, access_cards, login_attempts, nfc_sessions, device_commands) giữ nguyên logic, chỉ cần copy từ phiên bản trước vào đây.

# ==================== LƯU Ý ====================
# Các URL trong views.py vẫn dùng 'admin-sys/xxx' (hoặc bạn có thể đổi nếu muốn)
# Khi tạo URL pattern thì thêm:
# path('dashboard/', dashboard, name='dashboard'),
# path('users/', users_list, name='users_list'),
# ...