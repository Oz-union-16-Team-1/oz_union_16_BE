from django.db import models


class Game(models.Model):
    # 기본 정보
    game_id = models.BigIntegerField(primary_key=True, verbose_name="IGDB_게임_고유_ID")
    name = models.CharField(max_length=255, verbose_name="게임 이름")
    slug = models.CharField(max_length=255, verbose_name="슬러그")

    # 게임 설명 및 상태
    summary = models.TextField(null=True, blank=True, verbose_name="게임 개요")
    storyline = models.TextField(null=True, blank=True, verbose_name="게임 스토리라인")
    category = models.IntegerField(null=True, blank=True, verbose_name="게임 카테고리")
    status = models.IntegerField(null=True, blank=True, verbose_name="게임 출시 상태")

    # 날짜
    first_release_date = models.DateTimeField(
        null=True, blank=True, verbose_name="게임 출시일"
    )

    # 연관 콘텐츠 및 지원
    franchises = models.JSONField(null=True, blank=True, verbose_name="프랜차이즈 정보")
    version_title = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="버전 명"
    )
    remakes = models.JSONField(null=True, blank=True, verbose_name="리메이크 정보")
    remasters = models.JSONField(null=True, blank=True, verbose_name="리마스터 정보")
    expansions = models.JSONField(null=True, blank=True, verbose_name="확장팩 목록")
    dlcs = models.JSONField(null=True, blank=True, verbose_name="DLC 목록")
    language_supports = models.JSONField(
        null=True, blank=True, verbose_name="지원 언어"
    )

    # 평점 및 평가 지표 (REAL -> FloatField)
    rating = models.FloatField(null=True, blank=True, verbose_name="IGDB 평점")
    rating_count = models.IntegerField(
        null=True, blank=True, verbose_name="유저 평가 수"
    )
    aggregated_rating = models.FloatField(
        null=True, blank=True, verbose_name="전문가 평점"
    )
    aggregated_rating_count = models.IntegerField(
        null=True, blank=True, verbose_name="전문가 평가 수"
    )
    total_rating = models.FloatField(null=True, blank=True, verbose_name="통합 평점")
    total_rating_count = models.IntegerField(
        null=True, blank=True, verbose_name="통합 평가 수"
    )

    # 인기 지표
    follows = models.IntegerField(null=True, blank=True, verbose_name="팔로우 수")
    hypes = models.IntegerField(null=True, blank=True, verbose_name="기대 지수")

    # 상세 메타데이터 (모두 JSONB 대응)
    game_modes = models.JSONField(null=True, blank=True, verbose_name="게임 모드")
    player_perspectives = models.JSONField(
        null=True, blank=True, verbose_name="플레이어 시점"
    )
    themes = models.JSONField(null=True, blank=True, verbose_name="게임 테마")
    genres = models.JSONField(null=True, blank=True, verbose_name="게임 장르")
    keywords = models.JSONField(null=True, blank=True, verbose_name="게임 키워드")
    multiplayer_modes = models.JSONField(
        null=True, blank=True, verbose_name="멀티플레이 모드"
    )
    screenshots = models.JSONField(null=True, blank=True, verbose_name="스크린샷")
    videos = models.JSONField(null=True, blank=True, verbose_name="트레일러 영상")
    websites = models.JSONField(null=True, blank=True, verbose_name="게임 주소")
    involved_companies = models.JSONField(
        null=True, blank=True, verbose_name="관련 기업"
    )

    class Meta:
        db_table = "game_list"
        verbose_name = "게임 저장 테이블"
