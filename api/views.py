from rest_framework.response import Response

from api.utils import api_endpoint, require_auth


@api_endpoint("GET")
@require_auth
def index(request):
    """
    Does nothing. This endpoint exists just to test various functionalities throughout
    development.

    This should (hopefully) be removed by the time the API is ready for production.
    """
    return Response(
        {
            "message": [
                f"Hello, {request.user.email if request.user.email else 'Guest'}!"
            ]
        }
    )
