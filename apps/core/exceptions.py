from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotAuthenticated
from rest_framework.serializers import Serializer
from rest_framework.views import exception_handler


class ErrorResponseSerializer(serializers.Serializer):
    error_detail = serializers.CharField()


class ConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "이미 존재하는 데이터입니다."

    def __init__(self, field: str, detail: str):
        self.detail = {field: [detail]}


class AuthenticationFailedException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "비밀번호가 일치하지 않습니다."
    default_code = "authentication_failed"


def _flatten(value) -> str | dict:
    """
    ErrorDetail 리스트 또는 중첩 dict를 평탄화합니다.
    - list  → 첫 번째 항목을 str로 변환
    - dict  → 각 필드값을 재귀적으로 평탄화
    - 그 외 → str 변환
    """
    if isinstance(value, list):
        return str(value[0]) if value else ""
    if isinstance(value, dict):
        return {k: _flatten(v) for k, v in value.items()}
    return str(value)


# 예외 타입별 커스텀 메시지
CUSTOM_MESSAGES = {
    NotAuthenticated: "자격 인증 데이터가 제공되지 않았습니다.",
}


def custom_exception_handler(exc, context):
    # 예외 타입에 커스텀 메시지가 있으면 메시지를 교체한 뒤 처리
    if type(exc) in CUSTOM_MESSAGES:
        exc.detail = CUSTOM_MESSAGES[type(exc)]

    response = exception_handler(exc, context)

    if response is not None:
        data = response.data

        if isinstance(data, dict) and "detail" in data:
            # 401 / 403 등 단일 메시지
            response.data = {"error_detail": _flatten(data["detail"])}
        else:
            # 400 ValidationError / 409 ConflictException 등 필드 에러
            response.data = {"error_detail": _flatten(data)}

    return response
