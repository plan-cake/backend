from django.urls import path

from . import views

urlpatterns = [
    path("date-create/", views.create_date_event),
]
