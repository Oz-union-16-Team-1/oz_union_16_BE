from django.conf import settings
from django.db import models
from django.db.models import Q


class SurveyResult(models.Model):
    survey_results_id = models.BigAutoField(primary_key=True)
    survey_answer = (
        models.IntegerField()
    )  # 설문 결과 코드를 정수로 저장 (ex. PGTI 타입 ID, 점수 합산 결과 ID 등)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # survey_results는 사용자당 1건 (업데이트 형식)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_result",
    )

    class Meta:
        db_table = "survey_results"  # 음수 코드 방지 (최소 안전장치)
        constraints = [
            models.CheckConstraint(
                condition=Q(survey_answer__gte=0),
                name="ck_survey_results_answer_non_negative",
            ),
            # TODO: 결과값 범위 확정 시 상한 체크 추가 (ex. Q(survey_answer__lte=15))
        ]
