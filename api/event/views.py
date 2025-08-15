import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.event.utils import check_custom_code, generate_code
from api.settings import GENERIC_ERR_RESPONSE
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
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.IntegerField(required=False, min_value=15, max_value=60)
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=True)
    time_zone = serializers.CharField(required=True, max_length=64)
    custom_code = serializers.CharField(required=False, max_length=255)


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
    user = request.user
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_date = request.validated_data.get("start_date")
    end_date = request.validated_data.get("end_date")
    start_time = request.validated_data.get("start_time")
    end_time = request.validated_data.get("end_time")
    time_zone = request.validated_data.get("time_zone")
    custom_code = request.validated_data.get("custom_code")

    # Some extra input validation
    try:
        user_tz = ZoneInfo(time_zone)
        user_date = datetime.now(user_tz).date()
    except:
        return Response({"error": {"time_zone": ["Invalid time zone."]}}, status=400)
    if start_date < user_date:
        # By comparing to the user's local date, we ensure that they don't get blocked
        # from creating an event just because they're behind UTC
        return Response(
            {"error": {"start_date": ["start_date must be today or in the future."]}},
            status=400,
        )
    if start_date > end_date:
        return Response(
            {"error": {"end_date": ["end_date must be on or after start_date."]}},
            status=400,
        )
    if start_time >= end_time:
        return Response(
            {"error": {"end_time": ["end_time must be earlier than start_time."]}},
            status=400,
        )
    if duration and duration not in [15, 30, 60]:
        return Response(
            {
                "error": {
                    "duration": [
                        "duration must be one of the following values: 15, 30, 60."
                    ]
                }
            },
            status=400,
        )

    url_code = None
    if custom_code:
        error = check_custom_code(custom_code)
        if error:
            return Response({"error": {"custom_code": [error]}}, status=400)
        url_code = custom_code
    else:
        # Generate a random code if not provided
        try:
            url_code = generate_code()
        except:
            logger.critical("Failed to generate a unique URL code.")
            return GENERIC_ERR_RESPONSE

    return Response({"message": ["Event created successfully."]}, status=201)
