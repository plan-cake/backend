from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.availability.utils import get_weekday_date
from api.models import UserEvent
from api.utils import get_event_type


def format_event_info(event: UserEvent, time_zone: ZoneInfo):
    """
    Formats event info into a dictionary for the dashboard get endpoint.

    For query efficiency, the event's timeslots should be prefetched.
    """
    all_timeslots: list[datetime] = []

    event_type = get_event_type(event.date_type)
    match event.date_type:
        case UserEvent.EventType.SPECIFIC:
            all_timeslots = [
                ts.timeslot.astimezone(time_zone) for ts in event.date_timeslots.all()
            ]
        case UserEvent.EventType.GENERIC:
            all_timeslots = [
                get_weekday_date(ts.weekday, ts.timeslot).astimezone(time_zone)
                for ts in event.weekday_timeslots.all()
            ]

    # Earliest weekday is also sorted by date
    start_date = min(ts.date() for ts in all_timeslots)
    end_date = max(ts.date() for ts in all_timeslots)
    start_time = min(ts.time() for ts in all_timeslots)
    end_time = max(ts.time() for ts in all_timeslots)
    # End time should be 15 minutes after the last timeslot
    end_time = (datetime.combine(datetime.min, end_time) + timedelta(minutes=15)).time()

    data = {
        "title": event.title,
        "event_type": event_type,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "event_code": event.url_code.url_code,
        "time_zone": event.time_zone,
    }
    # Add extra fields only if not null, otherwise the serializer complains
    if event.duration:
        data["duration"] = event.duration

    return data
