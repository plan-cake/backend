import copy

from django.urls import get_resolver


def get_endpoints(urlpatterns, prefix=""):
    endpoints = []
    for pattern in urlpatterns:
        if hasattr(pattern, "url_patterns"):
            endpoints += get_endpoints(
                pattern.url_patterns, prefix + str(pattern.pattern)
            )
        else:
            pattern_copy = copy.copy(pattern)
            pattern_copy.pattern = prefix + str(pattern.pattern)
            endpoints.append(pattern_copy)
    return endpoints


def get_all_endpoints():
    return get_endpoints(get_resolver().url_patterns)


def get_readable_field_name(field_name):
    """
    Converts a serializer field to a standard data type.
    """
    match field_name:
        case "CharField":
            return "string"
        case "IntegerField":
            return "integer"
        case "BooleanField":
            return "boolean"
        case "DateField":
            return "date"
        case "DateTimeField":
            return "datetime"
        case "EmailField":
            return "string"
        case "ChoiceField":
            return "string"
        case "TimeZoneField":
            return "string"
        case "DictField":
            return "object"
        case _:
            return "object"


def get_field_info(field, include_required):
    data = {}
    if field.__class__.__name__ == "ListField":
        child = field.child
        data = {
            "type": "array",
            "items": get_field_info(child, include_required),
        }
        if include_required:
            data["required"] = field.required
    elif field.__class__.__name__ == "DictField":
        data = {
            "type": "map",
            "key": "string",
            "value": get_field_info(field.child, include_required=include_required),
        }
        if include_required:
            data["required"] = field.required
    elif (
        get_readable_field_name(field.__class__.__name__) == "object"
        and field.__class__.__name__ != "JSONField"
    ):
        # This is only for nested serializers
        data = {
            "type": "object",
            "properties": get_serializer_format(
                field.__class__, include_required=include_required
            ),
        }
    else:
        field_type = get_readable_field_name(field.__class__.__name__)
        data = {
            "type": field_type,
        }
        if include_required:
            data["required"] = field.required
    return data


def get_serializer_format(serializer_class, include_required=True):
    """
    Returns the format of the serializer class in a JSON format.
    """
    if not serializer_class:
        return None

    fields = {}
    for field_name, field in serializer_class().fields.items():
        fields[field_name] = get_field_info(field, include_required)
    return fields
