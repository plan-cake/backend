from django.urls import path

from . import views

urlpatterns = [
    path("add/", views.add_availability),
    path("check-display-name/", views.check_display_name),
    path("get-self/", views.get_self_availability),
    path("get-all/", views.get_all_availability),
]
