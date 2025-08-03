from django.urls import get_resolver


def get_endpoints(urlpatterns, prefix=""):
    endpoints = []
    for pattern in urlpatterns:
        if hasattr(pattern, "url_patterns"):
            endpoints += get_endpoints(
                pattern.url_patterns, prefix + str(pattern.pattern)
            )
        else:
            pattern.pattern = prefix + str(pattern.pattern)
            endpoints.append(pattern)
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
        case _:
            return "object"


def get_serializer_format(serializer_class, include_required=True):
    """
    Returns the format of the serializer class in a JSON format.
    """
    if not serializer_class:
        return None

    fields = {}
    for field_name, field in serializer_class().fields.items():
        if field.__class__.__name__ == "ListField":
            child = field.child.__class__.__name__
            child_type = get_readable_field_name(child)
            fields[field_name] = {
                "type": f"array",
                "items": {
                    "type": child_type,
                },
            }
            if child_type == "object" and child != "JSONField":
                fields[field_name]["items"]["properties"] = get_serializer_format(
                    field.child.__class__, include_required=include_required
                )
            if include_required:
                fields[field_name]["required"] = field.required
        else:
            field_type = get_readable_field_name(field.__class__.__name__)
            fields[field_name] = {
                "type": field_type,
            }
            if include_required:
                fields[field_name]["required"] = field.required
    return fields
