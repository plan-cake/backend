import logging

from django.db import DatabaseError, transaction
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.availability.serializers import (
    AvailabilityAddSerializer,
    AvailableDatesSerializer,
    DisplayNameCheckSerializer,
    EventAvailabilitySerializer,
    EventCodeSerializer,
)
from api.availability.utils import (
    EventGridDimensionError,
    check_name_available,
    get_event_grid,
    get_weekday_date,
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
@validate_output(AvailableDatesSerializer)
def get_self_availability(request):
    """
    Gets the availability submitted by the current user, in the form of a list of dates
    that the user is available.

    For 'week' events, the dates will be on the days of the week they represent.

    An error will be returned if the user has not participated in the specified event.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        participant = EventParticipant.objects.get(user_event=event, user_account=user)

        if event.date_type == UserEvent.EventType.SPECIFIC:
            availabilities = (
                EventDateAvailability.objects.filter(
                    event_participant=participant, is_available=True
                )
                .select_related("event_date_timeslot")
                .order_by("event_date_timeslot__timeslot")
            )
            data = [a.event_date_timeslot.timeslot for a in availabilities]
        else:
            availabilities = (
                EventWeekdayAvailability.objects.filter(
                    event_participant=participant, is_available=True
                )
                .select_related("event_weekday_timeslot")
                .order_by(
                    "event_weekday_timeslot__weekday",
                    "event_weekday_timeslot__timeslot",
                )
            )
            print(availabilities[0].event_weekday_timeslot.timeslot)
            print(type(availabilities[0].event_weekday_timeslot.timeslot))
            data = [
                get_weekday_date(
                    a.event_weekday_timeslot.weekday, a.event_weekday_timeslot.timeslot
                )
                for a in availabilities
            ]

        return Response({"available_dates": data}, status=200)

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


@api_endpoint("GET")
@require_auth
@validate_query_param_input(EventCodeSerializer)
@validate_output(EventAvailabilitySerializer)
def get_all_availability(request):
    """
    Gets the availability submitted by all event participants.

    The response format is a 3D array. The outermost layer is days, while the middle is
    timeslots and the innermost is the display names of available users for that timeslot.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        is_creator = event.user_account == user
        participants = event.participants.all()

        if not len(participants):
            _, num_days, num_times = get_event_grid(event)

            return Response(
                {
                    "is_creator": is_creator,
                    "participants": [],
                    "availability": [
                        [[] for _ in range(num_times)] for _ in range(num_days)
                    ],
                },
                status=200,
            )

        if event.date_type == UserEvent.EventType.SPECIFIC:
            availabilities = (
                EventDateAvailability.objects.filter(event_participant__in=participants)
                .select_related("event_date_timeslot")
                .order_by(
                    "event_date_timeslot__timeslot", "event_participant__display_name"
                )
            )
            timeslot_dict = {}
            for t in availabilities:
                timeslot = t.event_date_timeslot.timeslot
                if timeslot not in timeslot_dict:
                    timeslot_dict[timeslot] = []
                if t.is_available:
                    timeslot_dict[timeslot].append(t.event_participant.display_name)

            timeslots = sorted(timeslot_dict.keys())
            data = []
            current_day = [timeslot_dict[timeslots[0]]]
            last_date = timeslots[0].date()
            for timeslot in timeslots[1:]:
                timeslot_date = timeslot.date()
                if timeslot_date != last_date:
                    data.append(current_day)
                    current_day = []
                    last_date = timeslot_date
                current_day.append(timeslot_dict[timeslot])
            data.append(current_day)

            return Response(
                {
                    "is_creator": is_creator,
                    "participants": [p.display_name for p in participants],
                    "availability": data,
                },
                status=200,
            )
        else:
            availabilities = (
                EventWeekdayAvailability.objects.filter(
                    event_participant__in=participants
                )
                .select_related("event_weekday_timeslot")
                .order_by(
                    "event_weekday_timeslot__weekday",
                    "event_weekday_timeslot__timeslot",
                    "event_participant__display_name",
                )
            )
            timeslot_dict = {}
            for t in availabilities:
                timeslot = (
                    t.event_weekday_timeslot.weekday,
                    t.event_weekday_timeslot.timeslot,
                )
                if timeslot not in timeslot_dict:
                    timeslot_dict[timeslot] = []
                if t.is_available:
                    timeslot_dict[timeslot].append(t.event_participant.display_name)

            timeslots = sorted(timeslot_dict.keys())
            data = []
            current_day = [timeslot_dict[timeslots[0]]]
            last_weekday = timeslots[0][0]
            for timeslot in timeslots[1:]:
                timeslot_weekday = timeslot[0]
                if timeslot_weekday != last_weekday:
                    data.append(current_day)
                    current_day = []
                    last_weekday = timeslot_weekday
                current_day.append(timeslot_dict[timeslot])
            data.append(current_day)

            return Response(
                {
                    "is_creator": is_creator,
                    "participants": [p.display_name for p in participants],
                    "availability": data,
                },
                status=200,
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


@api_endpoint("POST")
@require_auth
@validate_json_input(EventCodeSerializer)
@validate_output(MessageOutputSerializer)
def remove_self_availability(request):
    """
    Removes the current user's availability for an event.

    An error will be returned if the user has not participated in the specified event.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        # Because of the foreign key cascades, this should remove everything
        EventParticipant.objects.get(user_event=event, user_account=user).delete()

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

    return Response({"message": ["Availability removed successfully."]}, status=200)


@api_endpoint("POST")
@require_auth
@validate_json_input(DisplayNameCheckSerializer)
@validate_output(MessageOutputSerializer)
def remove_availability(request):
    """
    Removes the specified user's availability for an event, identified by display name.

    This can only be done by the event creator.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")
    display_name = request.validated_data.get("display_name")

    try:
        event = UserEvent.objects.get(url_codes=event_code)
        if event.user_account != user:
            return Response(
                {"error": {"general": ["User must be event creator."]}}, status=403
            )
        # Because of the foreign key cascades, this should remove everything
        EventParticipant.objects.get(
            user_event=event, display_name=display_name
        ).delete()

    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except EventParticipant.DoesNotExist:
        return Response(
            {"error": {"general": ["Event participant not found."]}},
            status=404,
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Availability removed successfully."]}, status=200)
