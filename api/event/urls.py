from django.urls import path

from . import views

urlpatterns = [
    path("date-create/", views.create_date_event),
    path("week-create/", views.create_week_event),
    path("check-code/", views.check_code),
    path("date-edit/", views.edit_date_event),
    path("week-edit/", views.edit_week_event),
    path("get-details/", views.get_event_details),
]
