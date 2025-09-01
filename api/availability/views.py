import logging
from datetime import datetime

from django.db import DatabaseError, transaction
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.availability.serializers import (
    AvailabilityAddSerializer,
    AvailabilitySerializer,
    DisplayNameCheckSerializer,
    EventCodeSerializer,
)
from api.availability.utils import (
    EventGridDimensionError,
    check_name_available,
    get_event_grid,
)
from api.models import (
    EventDateAvailability,
    EventParticipant,
    EventWeekdayAvailability,
    UserEvent,
)
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    rate_limit,
    require_auth,
    validate_json_input,
    validate_output,
    validate_query_param_input,
)

logger = logging.getLogger("api")


class AvailabilityAddThrottle(AnonRateThrottle):
    scope = "availability_add"


class AvailabilityInputInvalidError(Exception):
    pass


@api_endpoint("POST")
@rate_limit(
    AvailabilityAddThrottle,
    "Availability submission limit reached ({rate}). Try again later.",
)
@require_auth
@validate_json_input(AvailabilityAddSerializer)
@validate_output(MessageOutputSerializer)
def add_availability(request):
    """
    Adds availability for the current user to an event. This endpoint supports both types
    of events.

    If the current user already added availability for the event, their data will be
    overridden.

    The availability must be supplied in a 2D array, with the outermost array representing
    days, and the innermost representing timeslots within that day.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")
    display_name = request.validated_data.get("display_name")
    availability = request.validated_data.get("availability")
    time_zone = request.validated_data.get("time_zone")

    try:
        with transaction.atomic():
            user_event = UserEvent.objects.get(url_codes=event_code)

            if not check_name_available(user_event, user, display_name):
                return Response(
                    {
                        "error": {
                            "display_name": ["Name is taken."],
                        }
                    },
                    status=400,
                )

            timeslots, num_days, num_times = get_event_grid(user_event)

            if len(availability) != num_days:
                raise AvailabilityInputInvalidError(
                    f"Invalid availability days. Expected {num_days}, got {len(availability)}."
                )
            for day in availability:
                if len(day) != num_times:
                    raise AvailabilityInputInvalidError(
                        f"Invalid availability timeslots. Expected {num_times}, got {len(day)}."
                    )

            participant, new = EventParticipant.objects.get_or_create(
                user_event=user_event,
                user_account=user,
                defaults={"time_zone": time_zone, "display_name": display_name},
            )
            if not new:
                participant.time_zone = time_zone
                participant.display_name = display_name
                participant.save()

            if user_event.date_type == UserEvent.EventType.SPECIFIC:
                EventDateAvailability.objects.filter(
                    event_participant=participant
                ).delete()
            else:
                EventWeekdayAvailability.objects.filter(
                    event_participant=participant
                ).delete()

            # Flatten the availability array to match the timeslots array format
            flattened_availability = [
                timeslot for day in availability for timeslot in day
            ]
            new_availabilities = []
            if user_event.date_type == UserEvent.EventType.SPECIFIC:
                for i, timeslot in enumerate(timeslots):
                    new_availabilities.append(
                        EventDateAvailability(
                            event_participant=participant,
                            event_date_timeslot=timeslot,
                            is_available=flattened_availability[i],
                        )
                    )
                EventDateAvailability.objects.bulk_create(new_availabilities)
            elif user_event.date_type == UserEvent.EventType.GENERIC:
                for i, timeslot in enumerate(timeslots):
                    new_availabilities.append(
                        EventWeekdayAvailability(
                            event_participant=participant,
                            event_weekday_timeslot=timeslot,
                            is_available=flattened_availability[i],
                        )
                    )
                EventWeekdayAvailability.objects.bulk_create(new_availabilities)

    except AvailabilityInputInvalidError as e:
        logger.warning(str(e) + " Event code: " + event_code)
        return Response(
            {
                "error": {
                    "availability": [str(e)],
                }
            },
            status=400,
        )
    except EventGridDimensionError as e:
        logger.critical(e)
        return GENERIC_ERR_RESPONSE
    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    logger.debug(
        f"Availability {'added' if new else 'updated'} for event with code: {event_code}"
    )
    return Response(
        {"message": [f"Availability {'added' if new else 'updated'} successfully."]},
        status=201,
    )


@api_endpoint("POST")
@require_auth
@validate_json_input(DisplayNameCheckSerializer)
@validate_output(MessageOutputSerializer)
def check_display_name(request):
    """
    Checks if a display name is available for an event.

    If the name is used by the current user, it will be considered available.

    Similarly to the "check_custom_code" endpoint, this should be called before trying to
    add availability to avoid errors and rate limits.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")
    display_name = request.validated_data.get("display_name")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        if check_name_available(event, user, display_name):
            return Response(
                {"message": ["Name is available."]},
                status=200,
            )
        else:
            return Response(
                {"error": {"display_name": ["Name is taken."]}},
                status=400,
            )
    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE


@api_endpoint("GET")
@require_auth
@validate_query_param_input(EventCodeSerializer)
@validate_output(AvailabilitySerializer)
def get_self_availability(request):
    """
    Gets the grid of availability submitted by the current user.

    An error will be returned if the user has not participated in the specified event.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        participant = EventParticipant.objects.get(user_event=event, user_account=user)

        if event.date_type == UserEvent.EventType.SPECIFIC:
            availabilities = (
                EventDateAvailability.objects.filter(event_participant=participant)
                .select_related("event_date_timeslot")
                .order_by("event_date_timeslot__timeslot")
            )
            data = []
            current_day = [availabilities[0].is_available]
            last_date = availabilities[0].event_date_timeslot.timeslot.date()
            for timeslot in availabilities[1:]:
                timeslot_date = timeslot.event_date_timeslot.timeslot.date()
                if timeslot_date != last_date:
                    data.append(current_day)
                    current_day = []
                    last_date = timeslot_date
                current_day.append(timeslot.is_available)
            data.append(current_day)

            return Response({"availability": data}, status=200)
        else:
            availabilities = (
                EventWeekdayAvailability.objects.filter(event_participant=participant)
                .select_related("event_weekday_timeslot")
                .order_by(
                    "event_weekday_timeslot__weekday",
                    "event_weekday_timeslot__timeslot",
                )
            )
            data = []
            current_day = [availabilities[0].is_available]
            last_weekday = availabilities[0].event_weekday_timeslot.weekday
            for timeslot in availabilities[1:]:
                timeslot_weekday = timeslot.event_weekday_timeslot.weekday
                if timeslot_weekday != last_weekday:
                    data.append(current_day)
                    current_day = []
                    last_weekday = timeslot_weekday
                current_day.append(timeslot.is_available)
            data.append(current_day)

            return Response({"availability": data}, status=200)

    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except EventParticipant.DoesNotExist:
        return Response(
            {"error": {"general": ["User has not participated in this event."]}},
            status=400,
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE
