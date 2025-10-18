import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import DatabaseError, transaction
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.event.serializers import (
    CustomCodeSerializer,
    DateEventCreateSerializer,
    DateEventEditSerializer,
    EventCodeSerializer,
    EventDetailSerializer,
    WeekEventCreateSerializer,
    WeekEventEditSerializer,
)
from api.event.utils import (
    check_custom_code,
    daterange,
    event_lookup,
    format_event_info,
    generate_code,
    timerange,
    validate_date_input,
    validate_weekday_input,
)
from api.models import (
    EventDateAvailability,
    EventDateTimeslot,
    EventWeekdayAvailability,
    EventWeekdayTimeslot,
    UrlCode,
    UserEvent,
)
from api.settings import GENERIC_ERR_RESPONSE, MAX_EVENT_DAYS
from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    check_auth,
    rate_limit,
    require_auth,
    validate_json_input,
    validate_output,
    validate_query_param_input,
)

logger = logging.getLogger("api")

EVENT_NOT_FOUND_ERROR = Response(
    {"error": {"general": ["Event not found."]}}, status=404
)


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

    user_date = datetime.now(ZoneInfo(time_zone)).date()
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
        except Exception:
            logger.critical("Failed to generate a unique URL code.")
            return GENERIC_ERR_RESPONSE

    try:
        with transaction.atomic():
            new_event = UserEvent.objects.create(
                user_account=user,
                title=title,
                date_type=UserEvent.EventType.SPECIFIC,
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
        except Exception:
            logger.critical("Failed to generate a unique URL code.")
            return GENERIC_ERR_RESPONSE

    try:
        with transaction.atomic():
            new_event = UserEvent.objects.create(
                user_account=user,
                title=title,
                date_type=UserEvent.EventType.GENERIC,
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


@api_endpoint("POST")
@check_auth
@validate_json_input(DateEventEditSerializer)
@validate_output(MessageOutputSerializer)
def edit_date_event(request):
    """
    Edits a 'date' type event, identified by its URL code.

    The event must be originally created by the current user.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_date = request.validated_data.get("start_date")
    end_date = request.validated_data.get("end_date")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")

    if not user:
        return EVENT_NOT_FOUND_ERROR

    user_date = datetime.now(ZoneInfo(time_zone)).date()
    try:
        # Do everything inside a transaction to ensure atomicity
        with transaction.atomic():
            # Find the event
            event = UserEvent.objects.get(
                url_code=event_code,
                user_account=user,
                date_type=UserEvent.EventType.SPECIFIC,
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
            if existing_start_date < user_date:
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
            to_add = [
                EventDateTimeslot(user_event=event, timeslot=ts)
                for ts in edited_timeslots - existing_timeslots
            ]
            EventDateTimeslot.objects.filter(
                user_event=event, timeslot__in=to_delete
            ).delete()
            EventDateTimeslot.objects.bulk_create(to_add)

            # Add in "unavailable" entries for the new timeslots for current participants
            to_add_availabilities = []
            for participant in event.participants.all():
                for ts in to_add:
                    to_add_availabilities.append(
                        EventDateAvailability(
                            event_participant=participant,
                            event_date_timeslot=ts,
                            is_available=False,
                        )
                    )
            EventDateAvailability.objects.bulk_create(to_add_availabilities)

    except UserEvent.DoesNotExist:
        return EVENT_NOT_FOUND_ERROR
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event updated with code: {event_code}")
    return Response({"message": ["Event updated successfully."]}, status=200)


@api_endpoint("POST")
@check_auth
@validate_json_input(WeekEventEditSerializer)
@validate_output(MessageOutputSerializer)
def edit_week_event(request):
    """
    Edits a 'week' type event, identified by its URL code.

    The event must be originally created by the current user.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")
    title = request.validated_data.get("title")
    duration = request.validated_data.get("duration")
    start_weekday = request.validated_data.get("start_weekday")
    end_weekday = request.validated_data.get("end_weekday")
    start_hour = request.validated_data.get("start_hour")
    end_hour = request.validated_data.get("end_hour")
    time_zone = request.validated_data.get("time_zone")

    if not user:
        return EVENT_NOT_FOUND_ERROR

    try:
        # Do everything inside a transaction to ensure atomicity
        with transaction.atomic():
            # Find the event
            event = UserEvent.objects.get(
                url_code=event_code,
                user_account=user,
                date_type=UserEvent.EventType.GENERIC,
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
            to_add = [
                EventWeekdayTimeslot(user_event=event, weekday=wd, timeslot=ts)
                for (wd, ts) in edited_timeslots - existing_timeslots
            ]

            if to_delete:
                # Make sure the query matches each unique weekday, timeslot pair
                query = Q()
                for wd, ts in to_delete:
                    query |= Q(user_event=event, weekday=wd, timeslot=ts)
                EventWeekdayTimeslot.objects.filter(query).delete()

            EventWeekdayTimeslot.objects.bulk_create(to_add)

            # Add in "unavailable" entries for the new timeslots for current participants
            to_add_availabilities = []
            for participant in event.participants.all():
                for ts in to_add:
                    to_add_availabilities.append(
                        EventWeekdayAvailability(
                            event_participant=participant,
                            event_weekday_timeslot=ts,
                            is_available=False,
                        )
                    )
            EventWeekdayAvailability.objects.bulk_create(to_add_availabilities)

    except UserEvent.DoesNotExist:
        return EVENT_NOT_FOUND_ERROR
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(f"Event updated with code: {event_code}")
    return Response({"message": ["Event updated successfully."]}, status=200)


@api_endpoint("GET")
@validate_query_param_input(EventCodeSerializer)
@validate_output(EventDetailSerializer)
def get_event_details(request):
    """
    Gets details about an event like title, duration, and date/time range.

    This is useful for both displaying an event, and preparing for event editing.

    start_date, end_date, start_weekday, and end_weekday will only have values for their
    corresponding event types.
    """
    event_code = request.validated_data.get("event_code")

    try:
        event = event_lookup(event_code)
        data = format_event_info(event)
    except UserEvent.DoesNotExist:
        return EVENT_NOT_FOUND_ERROR
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        data,
        status=200,
    )
