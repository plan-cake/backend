import logging

from django.db import DatabaseError
from django.db.models import Prefetch, Q
from rest_framework import serializers
from rest_framework.response import Response

from api.dashboard.utils import format_event_info
from api.event.serializers import EventDetailSerializer
from api.models import (
    EventDateTimeslot,
    EventParticipant,
    EventWeekdayTimeslot,
    UserEvent,
)
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import api_endpoint, check_auth, validate_output

logger = logging.getLogger("api")


class DashboardEventSerializer(EventDetailSerializer):
    event_code = serializers.CharField(required=True, max_length=255)


class DashboardSerializer(serializers.Serializer):
    created_events = serializers.ListField(
        child=DashboardEventSerializer(), required=True
    )
    participated_events = serializers.ListField(
        child=DashboardEventSerializer(), required=True
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
        created_events = (
            UserEvent.objects.filter(user_account=user, url_code__isnull=False)
            .order_by("created_at")
            .select_related("url_code")
            .prefetch_related(
                Prefetch(
                    "date_timeslots",
                    queryset=EventDateTimeslot.objects.order_by("timeslot"),
                ),
                Prefetch(
                    "weekday_timeslots",
                    queryset=EventWeekdayTimeslot.objects.order_by(
                        "weekday", "timeslot"
                    ),
                ),
            )
        )
        # Don't include events that the user both created and participated in
        participations = (
            EventParticipant.objects.filter(
                ~Q(user_event__user_account=user),
                user_account=user,
                user_event__url_code__isnull=False,
            )
            .order_by("user_event__created_at")
            .select_related("user_event__url_code")
            .prefetch_related(
                Prefetch(
                    "user_event__date_timeslots",
                    queryset=EventDateTimeslot.objects.order_by("timeslot"),
                ),
                Prefetch(
                    "user_event__weekday_timeslots",
                    queryset=EventWeekdayTimeslot.objects.order_by(
                        "weekday", "timeslot"
                    ),
                ),
            )
        )

        my_events = []
        for event in created_events:
            my_events.append(format_event_info(event))
            my_events[-1]["event_code"] = event.url_code.url_code
        their_events = []
        for event in participations:
            their_events.append(format_event_info(event.user_event))
            if event.user_event.url_code is not None:
                their_events[-1]["event_code"] = event.user_event.url_code.url_code

    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {"created_events": my_events, "participated_events": their_events}, status=200
    )
