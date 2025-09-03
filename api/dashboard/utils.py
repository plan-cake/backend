from api.models import UserEvent


def get_event_type(date_type):
    match date_type:
        case UserEvent.EventType.SPECIFIC:
            return "Date"
        case UserEvent.EventType.GENERIC:
            return "Week"


def format_event(event):
    return {
        "title": event.title,
        "event_type": get_event_type(event.date_type),
        "participants": [p.display_name for p in event.participants.all()],
        "event_code": event.url_codes.first().url_code,
    }
