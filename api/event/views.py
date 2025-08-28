import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import DatabaseError, transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.event.utils import (
    check_custom_code,
    daterange,
    generate_code,
    timerange,
    validate_date_input,
    validate_weekday_input,
)
from api.models import EventDateTimeslot, EventWeekdayTimeslot, UrlCode, UserEvent
from api.settings import GENERIC_ERR_RESPONSE, MAX_EVENT_DAYS
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
    duration = serializers.ChoiceField(required=False, choices=["15", "30", "45", "60"])
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    start_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    end_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    time_zone = serializers.CharField(required=True, max_length=64)
    custom_code = serializers.CharField(required=False, max_length=255)


class EventCodeSerializer(serializers.Serializer):
    event_code = serializers.CharField(required=True, max_length=255)


class EventCreateThrottle(AnonRateThrottle):
    scope = "event_creation"


@api_endpoint("POST")
@rate_limit(
    EventCreateThrottle, "Event creation limit reached ({rate}). Try again later."
)
@require_auth
@validate_json_input(DateEventCreateSerializer)
@validate_output(EventCodeSerializer)
def create_date_event(request):
    """
    Creates a 'date' type event that spans specific dates.

    If successful, the URL code for the event will be returned.

    A custom URL code can be specified, subject to availability. If unavailable, an error
    message is returned. Only alphanumeric characters and dashes are allowed.
    """
    user = request.user
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_date = request.validated_data.get("start_date")
    end_date = request.validated_data.get("end_date")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")
    custom_code = request.validated_data.get("custom_code")

    try:
        user_tz = ZoneInfo(time_zone)
        user_date = datetime.now(user_tz).date()
    except:
        return Response({"error": {"time_zone": ["Invalid time zone."]}})
    errors = validate_date_input(start_date, end_date, start_hour, end_hour, user_date)
    if errors.keys():
        return Response({"error": errors}, status=400)

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

    try:
        with transaction.atomic():
            new_event = UserEvent.objects.create(
                user_account=user,
                title=title,
                date_type="SPECIFIC",
                duration=duration,
                time_zone=time_zone,
            )
            # Here we trust the code checking logic from before instead of checking again
            UrlCode.objects.update_or_create(
                url_code=url_code, defaults={"user_event": new_event}
            )
            # Create timeslots for the date and time range
            timeslots = []
            for date in daterange(start_date, end_date):
                for time in timerange(start_hour, end_hour):
                    timeslots.append(
                        EventDateTimeslot(
                            user_event=new_event,
                            timeslot=datetime.combine(date, time),
                        )
                    )
            EventDateTimeslot.objects.bulk_create(timeslots)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event created with code: {url_code}")
    return Response({"event_code": url_code}, status=201)


class WeekEventCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.ChoiceField(required=False, choices=["15", "30", "45", "60"])
    start_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)
    end_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)
    start_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    end_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    time_zone = serializers.CharField(required=True, max_length=64)
    custom_code = serializers.CharField(required=False, max_length=255)


@api_endpoint("POST")
@rate_limit(
    EventCreateThrottle, "Event creation limit reached ({rate}). Try again later."
)
@require_auth
@validate_json_input(WeekEventCreateSerializer)
@validate_output(EventCodeSerializer)
def create_week_event(request):
    """
    Creates a 'week' type event that spans weekdays in a generic week.

    If successful, the URL code for the event will be returned.

    A custom URL code can be specified, subject to availability. If unavailable, an error
    message is returned. Only alphanumeric characters and dashes are allowed.
    """
    user = request.user
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_weekday = request.validated_data.get("start_weekday")
    end_weekday = request.validated_data.get("end_weekday")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")
    custom_code = request.validated_data.get("custom_code")

    # Some extra input validation
    try:
        ZoneInfo(time_zone)
    except:
        return Response({"error": {"time_zone": ["Invalid time zone."]}}, status=400)
    errors = validate_weekday_input(start_weekday, end_weekday, start_hour, end_hour)
    if errors.keys():
        return Response({"error": errors}, status=400)

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

    try:
        with transaction.atomic():
            new_event = UserEvent.objects.create(
                user_account=user,
                title=title,
                date_type="GENERIC",
                duration=duration,
                time_zone=time_zone,
            )
            # Here we trust the code checking logic from before instead of checking again
            UrlCode.objects.update_or_create(
                url_code=url_code, defaults={"user_event": new_event}
            )
            # Create timeslots for the date and time range
            timeslots = []
            for weekday in range(start_weekday, end_weekday + 1):
                for time in timerange(start_hour, end_hour):
                    timeslots.append(
                        EventWeekdayTimeslot(
                            user_event=new_event,
                            weekday=weekday,
                            timeslot=time,
                        )
                    )
            EventWeekdayTimeslot.objects.bulk_create(timeslots)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event created with code: {url_code}")
    return Response({"event_code": url_code}, status=201)


class CustomCodeSerializer(serializers.Serializer):
    custom_code = serializers.CharField(required=True, max_length=255)


@api_endpoint("POST")
@validate_json_input(CustomCodeSerializer)
@validate_output(MessageOutputSerializer)
def check_code(request):
    """
    Checks if a custom code is valid and available, and returns an error if not.

    This is useful for checking a code before creating an event, since an error when
    creating an event will count for the rate limit.
    """
    custom_code = request.validated_data.get("custom_code")
    error = check_custom_code(custom_code)
    if error:
        return Response({"error": {"custom_code": [error]}}, status=400)

    return Response({"message": ["Custom code is valid and available."]}, status=200)


class DateEventEditSerializer(serializers.Serializer):
    url_code = serializers.CharField(required=True, max_length=255)
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.ChoiceField(required=False, choices=["15", "30", "45", "60"])
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    start_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    end_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    time_zone = serializers.CharField(required=True, max_length=64)


@api_endpoint("POST")
@require_auth
@validate_json_input(DateEventEditSerializer)
@validate_output(MessageOutputSerializer)
def edit_date_event(request):
    """
    Edits a 'date' type event, identified by its URL code.

    The event must be originally created by the current user.
    """
    user = request.user
    url_code = request.validated_data.get("url_code")
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_date = request.validated_data.get("start_date")
    end_date = request.validated_data.get("end_date")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")

    try:
        user_tz = ZoneInfo(time_zone)
        user_date = datetime.now(user_tz).date()
    except:
        return Response({"error": {"time_zone": ["Invalid time zone."]}})

    try:
        # Do everything inside a transaction to ensure atomicity
        with transaction.atomic():
            # Find the event
            event = UserEvent.objects.get(
                url_codes=url_code, user_account=user, date_type="SPECIFIC"
            )
            # Get the earliest timeslot
            existing_start_date = (
                EventDateTimeslot.objects.filter(user_event=event)
                .order_by("timeslot")
                .first()
                .timeslot.date()
            )

            # If the start date is after today, it cannot be moved to a date earlier than today.
            # If the start date is before today, it cannot be moved earlier at all.
            earliest_date = user_date
            if existing_start_date > user_date:
                earliest_date = existing_start_date
            errors = validate_date_input(
                start_date, end_date, start_hour, end_hour, earliest_date, True
            )
            if errors.keys():
                return Response({"error": errors}, status=400)

            # Update the event object itself
            event.title = title
            event.duration = duration
            event.time_zone = time_zone
            event.save()

            # Sort out the timeslot difference
            existing_timeslots = set(
                EventDateTimeslot.objects.filter(user_event=event).values_list(
                    "timeslot", flat=True
                )
            )
            edited_timeslots = set(
                datetime.combine(date, time)
                for date in daterange(start_date, end_date)
                for time in timerange(start_hour, end_hour)
            )
            to_delete = existing_timeslots - edited_timeslots
            to_add = edited_timeslots - existing_timeslots
            EventDateTimeslot.objects.filter(
                user_event=event, timeslot__in=to_delete
            ).delete()
            EventDateTimeslot.objects.bulk_create(
                [EventDateTimeslot(user_event=event, timeslot=ts) for ts in to_add]
            )

    except UserEvent.DoesNotExist:
        return Response({"error": {"general": ["Event not found."]}}, status=404)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event updated with code: {url_code}")
    return Response({"message": ["Event updated successfully."]}, status=200)


class WeekEventEditSerializer(serializers.Serializer):
    url_code = serializers.CharField(required=True, max_length=255)
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.ChoiceField(required=False, choices=["15", "30", "45", "60"])
    start_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)
    end_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)
    start_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    end_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    time_zone = serializers.CharField(required=True, max_length=64)


@api_endpoint("POST")
@require_auth
@validate_json_input(WeekEventEditSerializer)
@validate_output(MessageOutputSerializer)
def edit_week_event(request):
    """
    Edits a 'week' type event, identified by its URL code.

    The event must be originally created by the current user.
    """
    user = request.user
    url_code = request.validated_data.get("url_code")
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_weekday = request.validated_data.get("start_weekday")
    end_weekday = request.validated_data.get("end_weekday")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")

    try:
        ZoneInfo(time_zone)
    except:
        return Response({"error": {"time_zone": ["Invalid time zone."]}})

    try:
        # Do everything inside a transaction to ensure atomicity
        with transaction.atomic():
            # Find the event
            event = UserEvent.objects.get(
                url_codes=url_code, user_account=user, date_type="GENERIC"
            )

            errors = validate_weekday_input(
                start_weekday, end_weekday, start_hour, end_hour
            )
            if errors.keys():
                return Response({"error": errors}, status=400)

            # Update the event object itself
            event.title = title
            event.duration = duration
            event.time_zone = time_zone
            event.save()

            # Sort out the timeslot difference
            existing_timeslots = set(
                EventWeekdayTimeslot.objects.filter(user_event=event).values_list(
                    "weekday", "timeslot"
                )
            )
            edited_timeslots = set(
                (weekday, time)
                for weekday in range(start_weekday, end_weekday + 1)
                for time in timerange(start_hour, end_hour)
            )
            to_delete = existing_timeslots - edited_timeslots
            to_add = edited_timeslots - existing_timeslots
            EventWeekdayTimeslot.objects.filter(
                user_event=event,
                weekday__in=[wd for wd, _ in to_delete],
                timeslot__in=[ts for _, ts in to_delete],
            ).delete()
            EventWeekdayTimeslot.objects.bulk_create(
                [
                    EventWeekdayTimeslot(user_event=event, weekday=wd, timeslot=ts)
                    for (wd, ts) in to_add
                ]
            )

    except UserEvent.DoesNotExist:
        return Response({"error": {"general": ["Event not found."]}}, status=404)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event updated with code: {url_code}")
    return Response({"message": ["Event updated successfully."]}, status=200)
