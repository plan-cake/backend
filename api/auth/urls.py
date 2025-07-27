from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register),
    path("verify-email/", views.verify_email),
    path("login/", views.login),
    path("check-password/", views.check_password),
    path("start-password-reset/", views.start_password_reset),
    path("reset-password/", views.reset_password),
    path("logout/", views.logout),
]
