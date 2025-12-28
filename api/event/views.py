import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import DatabaseError, transaction
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.availability.utils import get_weekday_date
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
    event_lookup,
    generate_code,
    js_weekday,
    validate_date_timeslots,
    validate_weekday_timeslots,
)
from api.models import EventDateTimeslot, EventWeekdayTimeslot, UrlCode, UserEvent
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    check_auth,
    get_event_type,
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

INVALID_TIMESLOT_TIME_ERROR = Response(
    {"error": {"timeslots": ["Timeslots must be on 15-minute intervals."]}},
    status=400,
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
    timeslots = request.validated_data.get("timeslots")
    time_zone = request.validated_data.get("time_zone")
    custom_code = request.validated_data.get("custom_code")

    user_date_local = datetime.now(ZoneInfo(time_zone)).date()
    errors = validate_date_timeslots(timeslots, user_date_local, time_zone)
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
            # Create timeslot objects
            EventDateTimeslot.objects.bulk_create(
                [
                    EventDateTimeslot(user_event=new_event, timeslot=ts)
                    for ts in set(timeslots)
                ]
            )
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
    timeslots = request.validated_data.get("timeslots")
    time_zone = request.validated_data.get("time_zone")
    custom_code = request.validated_data.get("custom_code")

    # Some extra input validation
    errors = validate_weekday_timeslots(timeslots)
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
            # Create timeslot objects
            deduplicated_timeslots = set(
                (js_weekday(ts.weekday()), ts.time()) for ts in timeslots
            )
            EventWeekdayTimeslot.objects.bulk_create(
                [
                    EventWeekdayTimeslot(
                        user_event=new_event,
                        weekday=weekday,
                        timeslot=time,
                    )
                    for (weekday, time) in deduplicated_timeslots
                ]
            )
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
    timeslots = request.validated_data.get("timeslots")
    time_zone = request.validated_data.get("time_zone")

    if not user:
        return EVENT_NOT_FOUND_ERROR

    user_date_local = datetime.now(ZoneInfo(time_zone)).date()
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
            earliest_timeslot = (
                EventDateTimeslot.objects.filter(user_event=event)
                .order_by("timeslot")
                .first()
            )
            existing_start_date: datetime = None
            if earliest_timeslot:
                existing_start_date = earliest_timeslot.timeslot
            else:
                logger.critical(
                    f"Event {event.id} has no timeslots when editing date event."
                )
                return GENERIC_ERR_RESPONSE
            # Convert it to local date for comparison
            existing_start_date = existing_start_date.astimezone(
                ZoneInfo(event.time_zone)
            ).date()

            # If the start date is after today, it cannot be moved to a date earlier than today.
            # If the start date is before today, it cannot be moved earlier at all.
            earliest_date_local = user_date_local
            if existing_start_date < user_date_local:
                earliest_date_local = existing_start_date
            errors = validate_date_timeslots(
                timeslots, earliest_date_local, time_zone, True
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
            edited_timeslots = set(timeslots)
            to_delete = existing_timeslots - edited_timeslots
            to_add = [
                EventDateTimeslot(user_event=event, timeslot=ts)
                for ts in edited_timeslots - existing_timeslots
            ]
            EventDateTimeslot.objects.filter(
                user_event=event, timeslot__in=to_delete
            ).delete()
            EventDateTimeslot.objects.bulk_create(to_add)

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
    timeslots = request.validated_data.get("timeslots")
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

            errors = validate_weekday_timeslots(timeslots)
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
                [(js_weekday(ts.weekday()), ts.time()) for ts in timeslots]
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
    Gets details about an event like title, duration, and timeslots.

    This is useful for both displaying an event, and preparing for event editing.
    """
    event_code = request.validated_data.get("event_code")

    try:
        event = event_lookup(event_code)
        data = {
            "title": event.title,
            "time_zone": event.time_zone,
            "event_type": get_event_type(event.date_type),
        }
        match event.date_type:
            case UserEvent.EventType.SPECIFIC:
                timeslots = event.date_timeslots.all()
                data["timeslots"] = [ts.timeslot for ts in timeslots]
            case UserEvent.EventType.GENERIC:
                timeslots = event.weekday_timeslots.all()
                data["timeslots"] = [
                    get_weekday_date(ts.weekday, ts.timeslot) for ts in timeslots
                ]

        if event.duration:
            data["duration"] = event.duration
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
