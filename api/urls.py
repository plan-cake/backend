from django.urls import include, path

from . import views

urlpatterns = [
    path("docs/", include("api.docs.urls")),
    path("auth/", include("api.auth.urls")),
    path("event/", include("api.event.urls")),
    path("availability/", include("api.availability.urls")),
    path("dashboard/", include("api.dashboard.urls")),
    path("account/", include("api.account.urls")),
]
