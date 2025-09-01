import logging

from django.db import DatabaseError, transaction
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.availability.serializers import DateAvailabilityAddSerializer
from api.availability.utils import EventGridDimensionError, get_event_grid
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
@validate_json_input(DateAvailabilityAddSerializer)
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
        logger.warning(e + " Event code: " + event_code)
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
