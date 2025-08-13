from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register),
    path("resend-register-email/", views.resend_register_email),
    path("verify-email/", views.verify_email),
    path("login/", views.login),
    path("check-password/", views.check_password),
    path("check-account-auth/", views.check_account_auth),
    path("start-password-reset/", views.start_password_reset),
    path("reset-password/", views.reset_password),
    path("logout/", views.logout),
    path("delete-account/", views.delete_account),
]
