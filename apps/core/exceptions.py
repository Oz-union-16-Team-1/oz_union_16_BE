from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class ConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "이미 존재하는 데이터입니다."


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {}

        if "detail" in response.data:
            error_data["error_detail"] = str(response.data["detail"])

        else:
            error_data["error_detail"] = response.data

        response.data = error_data

    return response
