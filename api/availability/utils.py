from api.models import EventDateTimeslot, EventWeekdayTimeslot, UserEvent


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
