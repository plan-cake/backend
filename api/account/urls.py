from django.urls import path

from . import views

urlpatterns = [
    path("set-default-name/", views.set_default_name),
    path("remove-default-name/", views.remove_default_name),
]
