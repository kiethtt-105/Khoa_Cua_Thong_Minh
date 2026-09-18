#backend/smartlock_backend/urls.py
from django.urls import path
from django.shortcuts import render

urlpatterns = [
    # ==================== ADMIN-SYS ====================
    path('login/', lambda request: render(request, 'admin/login.html')),
    path('dashboard/', lambda request: render(request, 'admin/dashboard.html')),
    path('users/', lambda request: render(request, 'admin/users.html')),
    path('devices/', lambda request: render(request, 'admin/devices.html')),
    path('support/', lambda request: render(request, 'admin/support.html')),
    
    # ==================== ACCOUNT PAGES ====================
    path('', lambda request: render(request, 'account/base/dashboard.html')),
    path('login/', lambda request: render(request, 'account/login.html')),
    path('register/', lambda request: render(request, 'account/register.html')),
    path('verify_email/', lambda request: render(request, 'account/verify_email.html')),
    path('reset_password/', lambda request: render(request, 'account/reset_password.html')),
    path('profile/', lambda request: render(request, 'account/profile.html')),
    path('dashboard/', lambda request: render(request, 'account/base/dashboard.html')),
    
    # Các trang khác
    path('devices/', lambda request: render(request, 'account/devices/list.html')),
    path('nfc/', lambda request: render(request, 'account/nfc/tags.html')),
    path('share/', lambda request: render(request, 'account/share/codes.html')),
    path('support/', lambda request: render(request, 'account/support/requests.html')),
    path('audit/', lambda request: render(request, 'account/audit/logs.html')),
    path('settings/', lambda request: render(request, 'account/settings/system.html')),
]