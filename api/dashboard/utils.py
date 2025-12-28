import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.availability.utils import get_weekday_date
from api.models import UserEvent
from api.utils import get_event_type

logger = logging.getLogger("api")


def format_event_info(event: UserEvent, user_time_zone: ZoneInfo):
    """
    Formats event info into a dictionary for the dashboard get endpoint.

    For query efficiency, the event's timeslots should be prefetched.
    """
    all_timeslots: list[datetime] = []
    event_time_zone = ZoneInfo(event.time_zone)

    event_type = get_event_type(event.date_type)
    # Sort the timeslots by the EVENT'S time zone to get the min/max of the creator
    match event.date_type:
        case UserEvent.EventType.SPECIFIC:
            all_timeslots = [
                ts.timeslot.astimezone(event_time_zone)
                for ts in event.date_timeslots.all()
            ]
        case UserEvent.EventType.GENERIC:
            all_timeslots = [
                get_weekday_date(ts.weekday, ts.timeslot).astimezone(event_time_zone)
                for ts in event.weekday_timeslots.all()
            ]

    if not all_timeslots:
        logger.critical(
            f"Event {event.id} has no timeslots when formatting for dashboard."
        )
        raise ValueError("Event has no timeslots.")

    # Earliest weekday is also sorted by date
    start_date = min(ts.date() for ts in all_timeslots)
    end_date = max(ts.date() for ts in all_timeslots)
    start_time = min(ts.time() for ts in all_timeslots)
    end_time = max(ts.time() for ts in all_timeslots)
    # End time should be 15 minutes after the last timeslot
    end_time = (datetime.combine(datetime.min, end_time) + timedelta(minutes=15)).time()

    # Then convert back to the user's local time zone for display
    # datetime.combine has no time zone info, so we include the event's time zone to
    # make sure it doesn't convert twice
    start_datetime = (
        datetime.combine(start_date, start_time)
        .replace(tzinfo=event_time_zone)
        .astimezone(user_time_zone)
    )
    end_datetime = (
        datetime.combine(end_date, end_time)
        .replace(tzinfo=event_time_zone)
        .astimezone(user_time_zone)
    )

    data = {
        "title": event.title,
        "event_type": event_type,
        "start_date": start_datetime.date(),
        "end_date": end_datetime.date(),
        "start_time": start_datetime.time(),
        "end_time": end_datetime.time(),
        "event_code": event.url_code.url_code if event.url_code else None,
        "time_zone": event.time_zone,
    }
    # Add extra fields only if not null, otherwise the serializer complains
    if event.duration:
        data["duration"] = event.duration

    return data
