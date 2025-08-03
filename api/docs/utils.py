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


def get_serializer_format(serializer_class):
    """
    Returns the format of the serializer class in a JSON format.
    """
    if not serializer_class:
        return None

    fields = {}
    TYPE_MAP = {
        "CharField": "string",
        "IntegerField": "integer",
        "BooleanField": "boolean",
        "DateField": "date",
        "DateTimeField": "datetime",
        "EmailField": "string",
    }
    for field_name, field in serializer_class().fields.items():
        field_type = TYPE_MAP.get(field.__class__.__name__, field.__class__.__name__)
        fields[field_name] = {
            "type": field_type,
            "required": field.required,
        }
    return fields
