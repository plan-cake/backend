from django.urls import path

from . import views

urlpatterns = [
    path("set-default-name/", views.set_default_name),
]
