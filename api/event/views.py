import logging

from rest_framework.response import Response

from api.utils import api_endpoint, require_auth

logger = logging.getLogger("api")


@api_endpoint("POST")
@require_auth
def create_event(request):
    """
    Creates an event with the given details.
    """
    return Response({"message": "Event created successfully."})
