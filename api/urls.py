from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.index),
    path("auth/", include("api.auth.urls")),
]
