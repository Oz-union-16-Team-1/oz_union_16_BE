from rest_framework.views import exception_handler


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
