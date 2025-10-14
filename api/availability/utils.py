from datetime import datetime

from django.db.models import Q

from api.models import (
    EventDateTimeslot,
    EventParticipant,
    EventWeekdayTimeslot,
    UserEvent,
)


class EventGridDimensionError(Exception):
    pass


def get_event_grid(event):
    timeslots = []
    num_days = 0
    if event.date_type == UserEvent.EventType.SPECIFIC:
        timeslots = EventDateTimeslot.objects.filter(user_event=event).order_by(
            "timeslot"
        )
        num_days = (
            timeslots.last().timeslot.date() - timeslots.first().timeslot.date()
        ).days + 1
    else:
        timeslots = EventWeekdayTimeslot.objects.filter(user_event=event).order_by(
            "weekday", "timeslot"
        )
        num_days = timeslots.last().weekday - timeslots.first().weekday + 1

    num_slots = timeslots.count() / num_days
    if timeslots.count() % num_days != 0:
        raise EventGridDimensionError(
            "Event timeslots are not evenly distributed across days."
        )
    return timeslots, int(num_days), int(num_slots)


def check_name_available(event, user, display_name):
    if user:
        existing_participant = EventParticipant.objects.filter(
            ~Q(user_account=user),
            user_event=event,
            display_name=display_name,
        ).first()
    else:
        existing_participant = EventParticipant.objects.filter(
            user_event=event,
            display_name=display_name,
        ).first()
    return existing_participant is None


def get_weekday_date(weekday, timeslot):
    return datetime(2012, 1, weekday + 1, timeslot.hour, timeslot.minute)
