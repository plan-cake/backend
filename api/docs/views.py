import inspect

from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.docs.utils import get_all_endpoints
from api.utils import APIMetadata


@api_view(["GET"])
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
        view_class = getattr(view, "view_class", "oops")
        metadata = getattr(view, "metadata", APIMetadata())
        method = "Any"
        if not isinstance(view_class, str):
            methods = [
                method.upper()
                for method in view_class.http_method_names
                if method != "options"
            ]
            method = methods[0] if methods else "Any"
        endpoints.append(
            {
                "path": "/" + str(pattern.pattern),
                "method": method,
                "description": desc if desc else "No description available.",
                "input_type": metadata.input_type,
                "input_format": "None",
                "min_auth_required": metadata.min_auth_required,
                "rate_limit": metadata.rate_limit,
            }
        )
    return Response({"data": endpoints})
