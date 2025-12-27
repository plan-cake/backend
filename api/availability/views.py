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
from api.availability.utils import check_name_available, get_timeslots, get_weekday_date
from api.models import (
    AvailabilityStatus,
    EventDateAvailability,
    EventParticipant,
    EventWeekdayAvailability,
    UserEvent,
)
from api.settings import GENERIC_ERR_RESPONSE
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


class AvailabilityAddThrottle(AnonRateThrottle):
    scope = "availability_add"


class InvalidTimeslotError(Exception):
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
            user_event = UserEvent.objects.get(url_code=event_code)

            if not check_name_available(user_event, user, display_name):
                return Response(
                    {
                        "error": {
                            "display_name": ["Name is taken."],
                        }
                    },
                    status=400,
                )

            timeslots = get_timeslots(user_event)

            participant, new = EventParticipant.objects.get_or_create(
                user_event=user_event,
                user_account=user,
                defaults={"time_zone": time_zone, "display_name": display_name},
            )
            if not new:
                participant.time_zone = time_zone
                participant.display_name = display_name
                participant.save()

            # Remove existing availability
            if user_event.date_type == UserEvent.EventType.SPECIFIC:
                EventDateAvailability.objects.filter(
                    event_participant=participant
                ).delete()
            else:
                EventWeekdayAvailability.objects.filter(
                    event_participant=participant
                ).delete()

            # Add new availability
            if user_event.date_type == UserEvent.EventType.SPECIFIC:
                timeslot_dict = {t.timeslot: t for t in timeslots}
                new_availabilities = []
                for timeslot in availability:
                    if timeslot not in timeslot_dict:
                        raise InvalidTimeslotError()
                    new_availabilities.append(
                        EventDateAvailability(
                            event_participant=participant,
                            event_date_timeslot=timeslot_dict[timeslot],
                            status=AvailabilityStatus.AVAILABLE,
                        )
                    )
                EventDateAvailability.objects.bulk_create(new_availabilities)
            elif user_event.date_type == UserEvent.EventType.GENERIC:
                timeslot_dict = {
                    get_weekday_date(t.weekday, t.timeslot): t for t in timeslots
                }
                new_availabilities = []
                for timeslot in availability:
                    if timeslot not in timeslot_dict:
                        raise InvalidTimeslotError()
                    new_availabilities.append(
                        EventWeekdayAvailability(
                            event_participant=participant,
                            event_weekday_timeslot=timeslot_dict[timeslot],
                            status=AvailabilityStatus.AVAILABLE,
                        )
                    )
                EventWeekdayAvailability.objects.bulk_create(new_availabilities)

    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except InvalidTimeslotError:
        return Response(
            {
                "error": {
                    "availability": [
                        "One or more timeslots are invalid, check if the event has been updated."
                    ]
                }
            },
            status=400,
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
@check_auth
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
        event = UserEvent.objects.get(url_code=event_code)
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


NOT_PARTICIPATED_ERROR = Response(
    {"error": {"general": ["User has not participated in this event."]}},
    status=400,
)


@api_endpoint("GET")
@check_auth
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

    # We can be ambiguous to avoid creating more guest accounts
    if not user:
        return NOT_PARTICIPATED_ERROR

    try:
        event = UserEvent.objects.get(url_code=event_code)
        participant = EventParticipant.objects.get(user_event=event, user_account=user)

        if event.date_type == UserEvent.EventType.SPECIFIC:
            availabilities = (
                EventDateAvailability.objects.filter(event_participant=participant)
                .select_related("event_date_timeslot")
                .order_by("event_date_timeslot__timeslot")
            )
            data = [a.event_date_timeslot.timeslot for a in availabilities]
        else:
            availabilities = (
                EventWeekdayAvailability.objects.filter(event_participant=participant)
                .select_related("event_weekday_timeslot")
                .order_by(
                    "event_weekday_timeslot__weekday",
                    "event_weekday_timeslot__timeslot",
                )
            )
            data = [
                get_weekday_date(
                    a.event_weekday_timeslot.weekday, a.event_weekday_timeslot.timeslot
                )
                for a in availabilities
            ]

        return Response(
            {
                "display_name": participant.display_name,
                "available_dates": data,
                "time_zone": participant.time_zone,
            },
            status=200,
        )

    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except EventParticipant.DoesNotExist:
        return NOT_PARTICIPATED_ERROR
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE


@api_endpoint("GET")
@check_auth
@validate_query_param_input(EventCodeSerializer)
@validate_output(EventAvailabilitySerializer)
def get_all_availability(request):
    """
    Gets the availability submitted by all event participants.

    The response format is a dictionary of arrays. The keys are timeslots (in ISO format)
    and the values are arrays of the display names of available users for that timeslot.

    The "user_display_name" field is the display name of the current user. If the user
    has not participated in the event, this will be null.

    The "is_creator" field indicates whether the current user is the creator of the event.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    user_display_name = None

    try:
        event = UserEvent.objects.get(url_code=event_code)
        is_creator = event.user_account == user
        participants = event.participants.all()

        # Prep the dictionary with empty arrays for the return value
        availability_dict = {}
        timeslots = get_timeslots(event)
        if event.date_type == UserEvent.EventType.SPECIFIC:
            for slot in timeslots:
                availability_dict[slot.timeslot.isoformat()] = []
        else:
            for slot in timeslots:
                availability_dict[
                    get_weekday_date(slot.weekday, slot.timeslot).isoformat()
                ] = []

        if not len(participants):
            return Response(
                {
                    "is_creator": is_creator,
                    "user_display_name": user_display_name,
                    "participants": [],
                    "availability": availability_dict,
                },
                status=200,
            )

        # Check if the user is a participant to get their display name
        # This checks after the empty participants check to avoid unnecessary queries
        if user:
            participant = participants.filter(user_account=user).first()
            user_display_name = participant.display_name if participant else None

        if event.date_type == UserEvent.EventType.SPECIFIC:
            availabilities = (
                EventDateAvailability.objects.filter(event_participant__in=participants)
                .select_related("event_date_timeslot", "event_participant")
                .order_by(
                    "event_date_timeslot__timeslot", "event_participant__display_name"
                )
            )
            for t in availabilities:
                timeslot = t.event_date_timeslot.timeslot.isoformat()
                if timeslot not in availability_dict:
                    logger.error(
                        f"Timeslot {timeslot} not found in availability dict for event {event_code}"
                    )
                    continue
                availability_dict[timeslot].append(t.event_participant.display_name)

            return Response(
                {
                    "is_creator": is_creator,
                    "user_display_name": user_display_name,
                    "participants": [p.display_name for p in participants],
                    "availability": availability_dict,
                },
                status=200,
            )
        else:
            availabilities = (
                EventWeekdayAvailability.objects.filter(
                    event_participant__in=participants
                )
                .select_related("event_weekday_timeslot", "event_participant")
                .order_by(
                    "event_weekday_timeslot__weekday",
                    "event_weekday_timeslot__timeslot",
                    "event_participant__display_name",
                )
            )
            for t in availabilities:
                timeslot = get_weekday_date(
                    t.event_weekday_timeslot.weekday,
                    t.event_weekday_timeslot.timeslot,
                ).isoformat()
                if timeslot not in availability_dict:
                    logger.error(
                        f"Timeslot {timeslot} not found in availability dict for event {event_code}"
                    )
                    continue
                availability_dict[timeslot].append(t.event_participant.display_name)

            return Response(
                {
                    "is_creator": is_creator,
                    "user_display_name": user_display_name,
                    "participants": [p.display_name for p in participants],
                    "availability": availability_dict,
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
@check_auth
@validate_json_input(EventCodeSerializer)
@validate_output(MessageOutputSerializer)
def remove_self_availability(request):
    """
    Removes the current user's availability for an event.

    An error will be returned if the user has not participated in the specified event.
    """
    user = request.user
    event_code = request.validated_data.get("event_code")

    if not user:
        return NOT_PARTICIPATED_ERROR

    try:
        event = UserEvent.objects.get(url_code=event_code)
        # Because of the foreign key cascades, this should remove everything
        EventParticipant.objects.get(user_event=event, user_account=user).delete()

    except UserEvent.DoesNotExist:
        return Response(
            {"error": {"event_code": ["Event not found."]}},
            status=404,
        )
    except EventParticipant.DoesNotExist:
        return NOT_PARTICIPATED_ERROR
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Availability removed successfully."]}, status=200)


@api_endpoint("POST")
@check_auth
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

    NOT_CREATOR_ERROR = Response(
        {"error": {"general": ["User must be event creator."]}}, status=403
    )

    if not user:
        return NOT_CREATOR_ERROR

    try:
        event = UserEvent.objects.get(url_code=event_code)
        if event.user_account != user:
            return NOT_CREATOR_ERROR
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
