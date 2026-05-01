import uuid
from typing import TypedDict

from rest_framework.exceptions import ValidationError

from apps.core.utils.s3_handler import S3Handler

ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]

CONTENT_TYPE_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class PresignedUrlResult(TypedDict):
    presigned_url: str
    img_url: str
    key: str


class PresignedUrlService:
    _s3_handler: S3Handler | None = None

    @classmethod
    def get_s3_handler(cls) -> S3Handler:
        if cls._s3_handler is None:
            cls._s3_handler = S3Handler()
        return cls._s3_handler

    @classmethod
    def create(
        cls, folder: str, file_name: str, content_type: str
    ) -> PresignedUrlResult:
        extension = file_name.split(".")[-1].lower()

        if not extension or extension not in ALLOWED_EXTENSIONS:
            raise ValidationError("지원하지 않는 파일 형식입니다.")

        expected_content_type = CONTENT_TYPE_MAP[extension]
        if content_type != expected_content_type:
            raise ValidationError(
                f"content_type이 올바르지 않습니다. {extension} 파일은 {expected_content_type}이어야 합니다."
            )

        key = f"uploads/images/{folder}/{uuid.uuid4()}.{extension}"

        handler = cls.get_s3_handler()
        presigned_url = handler.generate_presigned_url(
            key=key, content_type=content_type
        )
        img_url = handler.get_img_url(key=key)

        return PresignedUrlResult(
            presigned_url=presigned_url,
            img_url=img_url,
            key=key,
        )

    @staticmethod
    def update_profile_image(user, profile_img_url: str) -> None:
        user.profile_img_url = profile_img_url
        user.save(update_fields=["profile_img_url"])
