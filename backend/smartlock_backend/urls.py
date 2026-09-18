# smartlock/smartlock_backend/urls.py
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', include('smartlock.urls', namespace='smartlock')),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='account/base/reset_password.html'), name='password_reset'),
    path('', include('smartlock.urls', namespace='smartlock')),
]