import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        abstract = True


# UUID를 기본 PK로 사용하는 공통 모델 추가
class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


# 만약 시간과 UUID가 모두 필요한 모델이 많다면 합쳐진 모델도 유용합니다.
class BaseUUIDModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True
