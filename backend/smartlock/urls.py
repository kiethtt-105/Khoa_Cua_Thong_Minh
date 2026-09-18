#backend/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

urlpatterns = [
    # ==================== ADMIN-SYS ====================
    path('admin-sys/', include('smartlock_backend.urls')),
    
    # ==================== ACCOUNT PAGES ====================
    path('', lambda request: render(request, 'account/base/dashboard.html')),
    path('account/login/', lambda request: render(request, 'account/login.html')),
    path('account/register/', lambda request: render(request, 'account/register.html')),
    path('account/verify_email/', lambda request: render(request, 'account/verify_email.html')),
    path('account/reset_password/', lambda request: render(request, 'account/reset_password.html')),
    path('account/profile/', lambda request: render(request, 'account/profile.html')),
    path('account/dashboard/', lambda request: render(request, 'account/base/dashboard.html')),
    
    # ==================== ADMIN PAGES ====================
    path('admin-sys/login/', lambda request: render(request, 'admin/login.html')),
    path('admin-sys/dashboard/', lambda request: render(request, 'admin/dashboard.html')),
    path('admin-sys/users/', lambda request: render(request, 'admin/users.html')),
    path('admin-sys/devices/', lambda request: render(request, 'admin/devices.html')),
    path('admin-sys/support/', lambda request: render(request, 'admin/support.html')),
    
    # Các trang khác
    path('devices/', lambda request: render(request, 'account/devices/list.html')),
    path('nfc/', lambda request: render(request, 'account/nfc/tags.html')),
    path('share/', lambda request: render(request, 'account/share/codes.html')),
    path('support/', lambda request: render(request, 'account/support/requests.html')),
    path('audit/', lambda request: render(request, 'account/audit/logs.html')),
    path('settings/', lambda request: render(request, 'account/settings/system.html')),
]