from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.index),
    path("docs/", include("api.docs.urls")),
    path("auth/", include("api.auth.urls")),
    path("event/", include("api.event.urls")),
]
