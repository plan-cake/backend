import inspect

from rest_framework.response import Response

from api.docs.utils import get_all_endpoints, get_serializer_format
from api.utils import APIMetadata, api_endpoint


@api_endpoint("GET")
def get_docs(request):
    """
    Dynamically generates documentation for all API endpoints. Returns a list of endpoints
    with their paths, allowed methods, descriptions, input specifications, authentication
    requirements, and rate limits.
    """
    all_endpoints = get_all_endpoints()
    endpoints = []
    for pattern in all_endpoints:
        view = pattern.callback
        desc = inspect.getdoc(view)  # Used for reliability instead of getattr
        metadata = getattr(view, "metadata", APIMetadata())
        endpoints.append(
            {
                "path": "/" + str(pattern.pattern),
                "method": metadata.method,
                "description": desc if desc else "No description available.",
                "input_type": metadata.input_type,
                "input_format": get_serializer_format(metadata.input_serializer_class),
                "min_auth_required": metadata.min_auth_required,
                "rate_limit": metadata.rate_limit,
            }
        )
    return Response({"data": endpoints})
