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
