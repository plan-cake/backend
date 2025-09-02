import logging

from django.db import DatabaseError
from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response

from api.models import EventParticipant, UserEvent
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import api_endpoint, require_auth, validate_output

logger = logging.getLogger("api")


class EventSerializer(serializers.Serializer):
    title = serializers.CharField(required=True)
    event_type = serializers.ChoiceField(required=True, choices=["Date", "Week"])
    participants = serializers.ListField(
        child=serializers.CharField(required=True, max_length=25), required=True
    )
    event_code = serializers.CharField(required=True, max_length=255)


class DashboardSerializer(serializers.Serializer):
    created_events = serializers.ListField(child=EventSerializer(), required=True)
    participated_events = serializers.ListField(child=EventSerializer(), required=True)


@api_endpoint("GET")
@require_auth
@validate_output(DashboardSerializer)
def get_dashboard(request):
    """
    Returns dashboard data for the current user. This includes events that the user
    created and ones that the user participated in.

    Events that no longer have a URL code from inactivity will not be included.
    """
    user = request.user

    try:
        created_events = UserEvent.objects.filter(
            user_account=user, url_codes__isnull=False
        )
        # Don't include events that the user both created and participated in
        participated_events = EventParticipant.objects.filter(
            ~Q(user_event__user_account=user),
            user_account=user,
            user_event__url_codes__isnull=False,
        )

        my_events = [
            {
                "title": event.title,
                "event_type": ("Date" if event.date_type == "SPECIFIC" else "Week"),
                "participants": [p.display_name for p in event.participants.all()],
                "event_code": event.url_codes.first().url_code,
            }
            for event in created_events
        ]
        their_events = [
            {
                "title": event.user_event.title,
                "event_type": (
                    "Date" if event.user_event.date_type == "SPECIFIC" else "Week"
                ),
                "participants": [
                    p.display_name for p in event.user_event.participants.all()
                ],
                "event_code": event.user_event.url_codes.first().url_code,
            }
            for event in participated_events
        ]

    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"created_events": my_events, "participated_events": their_events})
