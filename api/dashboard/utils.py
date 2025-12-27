from api.models import UserEvent
from api.utils import get_event_type


def format_event_info(
    event: UserEvent,
):
    """
    Formats event info into a dictionary to satisfy the output serializers on certain
    endpoints.

    For query efficiency, the event's timeslots should be prefetched.
    """
    start_date = None
    end_date = None
    start_weekday = None
    end_weekday = None
    event_type = ""
    start_hour = -1
    end_hour = -1

    event_type = get_event_type(event.date_type)
    first_timeslot = None
    last_timeslot = None
    match event_type:
        case "Date":
            all_timeslots = list(event.date_timeslots.all())
            first_timeslot = all_timeslots[0]
            last_timeslot = all_timeslots[-1]
            start_date = first_timeslot.timeslot.date()
            end_date = last_timeslot.timeslot.date()
        case "Week":
            all_timeslots = list(event.weekday_timeslots.all())
            first_timeslot = all_timeslots[0]
            last_timeslot = all_timeslots[-1]
            start_weekday = first_timeslot.weekday
            end_weekday = last_timeslot.weekday

    start_hour = first_timeslot.timeslot.hour
    # The last timeslot will always be XX:45, so just add 1 to the hour
    end_hour = last_timeslot.timeslot.hour + 1

    data = {
        "title": event.title,
        "event_type": event_type,
        "start_hour": start_hour,
        "end_hour": end_hour,
        "time_zone": event.time_zone,
    }
    # Add the extra fields only if not null, otherwise the serializer complains
    if event.duration:
        data["duration"] = event.duration
    if start_date:
        data["start_date"] = start_date
    if end_date:
        data["end_date"] = end_date
    if start_weekday is not None:
        data["start_weekday"] = start_weekday
    if end_weekday is not None:
        data["end_weekday"] = end_weekday

    return data
