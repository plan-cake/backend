import logging

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    rate_limit,
    require_auth,
    validate_json_input,
    validate_output,
)

logger = logging.getLogger("api")


class DateEventCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=True)
    duration = serializers.IntegerField(required=False)
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=True)
    time_zone = serializers.CharField(required=True)
    custom_code = serializers.CharField(required=False)


class EventCreateThrottle(AnonRateThrottle):
    scope = "event_creation"


@api_endpoint("POST")
@rate_limit(
    EventCreateThrottle, "Event creation limit reached ({rate}). Try again later."
)
@require_auth
@validate_json_input(DateEventCreateSerializer)
@validate_output(MessageOutputSerializer)
def create_date_event(request):
    """
    Creates a 'date' type event that spans specific dates.
    """
    return Response({"message": "Event created successfully."}, status=201)
