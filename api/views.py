from rest_framework.response import Response
from rest_framework.decorators import api_view

from api.utils import require_auth


@api_view(["GET"])
@require_auth
def index(request):
    return Response({"message": [f"Hello, {request.user.email}!"]})
