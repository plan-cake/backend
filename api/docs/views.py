import inspect

from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.docs.utils import get_all_endpoints
from api.utils import APIMetadata


@api_view(["GET"])
def get_docs(request):
    """
    Dynamically generates documentation for all API endpoints. Returns a list of endpoints
    with their paths, documentation strings, and allowed HTTP methods.
    """
    all_endpoints = get_all_endpoints()
    endpoints = []
    for pattern in all_endpoints:
        view = pattern.callback
        doc = inspect.getdoc(view)  # Used for reliability instead of getattr
        view_class = getattr(view, "view_class", "oops")
        metadata = getattr(view, "metadata", APIMetadata())
        methods = []
        if not isinstance(view_class, str):
            methods = [
                method.upper()
                for method in view_class.http_method_names
                if method != "options"
            ]
        endpoints.append(
            {
                "path": "/" + str(pattern.pattern),
                "doc": doc if doc else "No documentation available.",
                "methods": methods,
                "input_type": metadata.input_type,
                "min_auth_required": metadata.min_auth_required,
                "rate_limit": metadata.rate_limit,
            }
        )
    return Response({"data": endpoints})
