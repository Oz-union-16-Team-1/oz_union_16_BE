from rest_framework import serializers

from apps.survey.constants import (
    SURVEY_RECOMMENDATION_DEFAULT_PAGE_SIZE,
    SURVEY_RECOMMENDATION_MAX_PAGE_SIZE,
)


class SurveyRecommendationQuerySerializer(serializers.Serializer):
    cursor = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.IntegerField(
        required=False,
        default=SURVEY_RECOMMENDATION_DEFAULT_PAGE_SIZE,
        min_value=1,
        max_value=SURVEY_RECOMMENDATION_MAX_PAGE_SIZE,
    )


class SurveyRecommendationGameSerializer(serializers.Serializer):
    game_id = serializers.IntegerField()
    title = serializers.CharField()
    genres = serializers.ListField(child=serializers.CharField())
    thumbnail_url = serializers.CharField(allow_null=True)
    rating = serializers.FloatField(allow_null=True)
    is_liked = serializers.BooleanField()


class SurveyRecommendationResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    results = SurveyRecommendationGameSerializer(many=True)
