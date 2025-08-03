import inspect

from rest_framework import serializers
from rest_framework.response import Response

from api.docs.utils import get_all_endpoints, get_serializer_format
from api.utils import APIMetadata, api_endpoint, validate_output


class EndpointSerializer(serializers.Serializer):
    path = serializers.CharField()
    method = serializers.CharField()
    description = serializers.CharField()
    input_type = serializers.CharField(allow_null=True)
    input_format = serializers.JSONField(allow_null=True)
    output_format = serializers.JSONField(allow_null=True)
    min_auth_required = serializers.CharField(allow_null=True)
    rate_limit = serializers.CharField(allow_null=True)


class DocsSerializer(serializers.Serializer):
    data = serializers.ListField(child=EndpointSerializer())


@api_endpoint("GET")
@validate_output(DocsSerializer)
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
                "output_format": get_serializer_format(
                    metadata.output_serializer_class, include_required=False
                ),
                "min_auth_required": metadata.min_auth_required,
                "rate_limit": metadata.rate_limit,
            }
        )
    return Response({"data": endpoints})
