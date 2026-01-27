import logging

from django.db import DatabaseError, transaction
from rest_framework.response import Response

from api.availability.serializers import DisplayNameSerializer
from api.settings import GENERIC_ERR_RESPONSE
from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    require_account_auth,
    validate_json_input,
    validate_output,
)

logger = logging.getLogger("api")


@api_endpoint("POST")
@require_account_auth
@validate_json_input(DisplayNameSerializer)
@validate_output(MessageOutputSerializer)
def set_default_name(request):
    """
    Sets the default display name for the authenticated user account.
    """
    user = request.user
    display_name = request.validated_data["display_name"]

    try:
        with transaction.atomic():
            user.default_display_name = display_name
            user.save()
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {"message": ["Default name set successfully."]},
        status=200,
    )


@api_endpoint("POST")
@require_account_auth
@validate_output(MessageOutputSerializer)
def remove_default_name(request):
    """
    Removes the default display name for the authenticated user account.
    """
    user = request.user

    try:
        with transaction.atomic():
            user.default_display_name = None
            user.save()
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {"message": ["Default name removed successfully."]},
        status=200,
    )
