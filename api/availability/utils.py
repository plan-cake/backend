from datetime import datetime

from django.db.models import Q

from api.models import (
    EventDateTimeslot,
    EventParticipant,
    EventWeekdayTimeslot,
    UserEvent,
)


def get_timeslots(event):
    timeslots = []
    if event.date_type == UserEvent.EventType.SPECIFIC:
        timeslots = EventDateTimeslot.objects.filter(user_event=event).order_by(
            "utc_timeslot"
        )
    else:
        timeslots = EventWeekdayTimeslot.objects.filter(user_event=event).order_by(
            "weekday", "local_timeslot"
        )

    return timeslots


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
