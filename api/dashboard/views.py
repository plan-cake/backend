import logging

from django.db import DatabaseError
from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response

from api.event.serializers import EventDetailSerializer
from api.event.utils import format_event_info
from api.models import EventParticipant, UserEvent
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import api_endpoint, check_auth, validate_output

logger = logging.getLogger("api")


class DashboardSerializer(serializers.Serializer):
    created_events = serializers.ListField(child=EventDetailSerializer(), required=True)
    participated_events = serializers.ListField(
        child=EventDetailSerializer(), required=True
    )


@api_endpoint("GET")
@check_auth
@validate_output(DashboardSerializer)
def get_dashboard(request):
    """
    Returns dashboard data for the current user. This includes events that the user
    created and ones that the user participated in.

    The events are sorted by their creation date.

    Events that no longer have a URL code from inactivity will not be included.
    """
    user = request.user

    if not user:
        return Response(
            {
                "created_events": [],
                "participated_events": [],
            },
            status=200,
        )

    try:
        created_events = UserEvent.objects.filter(
            user_account=user, url_codes__isnull=False
        ).order_by("created_at")
        # Don't include events that the user both created and participated in
        participants = EventParticipant.objects.filter(
            ~Q(user_event__user_account=user),
            user_account=user,
            user_event__url_codes__isnull=False,
        ).order_by("user_event__created_at")

        my_events = [format_event_info(event) for event in created_events]
        their_events = [
            format_event_info(participant.user_event) for participant in participants
        ]

    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {"created_events": my_events, "participated_events": their_events}, status=200
    )
