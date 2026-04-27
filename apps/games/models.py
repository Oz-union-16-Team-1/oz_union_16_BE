from django.db import models


class Game(models.Model):
    # 1~3: 기본 식별 정보
    game_id = models.BigIntegerField(primary_key=True, verbose_name="IGDB_게임_고유_ID")
    name = models.CharField(max_length=255, verbose_name="게임 이름")
    slug = models.CharField(max_length=255, verbose_name="슬러그")

    # 4~7: 개요 및 상태
    summary = models.TextField(null=True, blank=True, verbose_name="게임 개요")
    storyline = models.TextField(null=True, blank=True, verbose_name="게임 스토리라인")
    category = models.IntegerField(null=True, blank=True, verbose_name="게임 카테고리")
    status = models.IntegerField(null=True, blank=True, verbose_name="게임 출시 상태")

    # 8: 출시일
    first_release_date = models.DateTimeField(
        null=True, blank=True, verbose_name="게임 출시일"
    )

    # 9~15: 연관 콘텐츠 및 지원 (JSONB)
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

    # 16~21: 평점 데이터 (명세서 REAL -> FloatField)
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

    # 22~23: 인기 지수
    follows = models.IntegerField(null=True, blank=True, verbose_name="팔로우 수")
    hypes = models.IntegerField(null=True, blank=True, verbose_name="기대 지수")

    # 24~33: 상세 메타데이터 (JSONB)
    game_modes = models.JSONField(null=True, blank=True, verbose_name="게임 모드")
    player_perspectives = models.JSONField(
        null=True, blank=True, verbose_name="플레이어 시점"
    )
    themes = models.JSONField(null=True, blank=True, verbose_name="게임 테마")
    genres = models.JSONField(null=True, blank=True, verbose_name="게임 장르")
    platforms = models.JSONField(null=True, blank=True, verbose_name="지원 플랫폼")
    keywords = models.JSONField(null=True, blank=True, verbose_name="게임 키워드")
    multiplayer_modes = models.JSONField(
        null=True, blank=True, verbose_name="멀티플레이 모드"
    )
    screenshots = models.JSONField(null=True, blank=True, verbose_name="스크린샷")
    videos = models.JSONField(null=True, blank=True, verbose_name="트레일러 영상")
    websites = models.JSONField(null=True, blank=True, verbose_name="게임 주소")
    involved_companies = models.JSONField(
        null=True, blank=True, verbose_name="관련 기업 정보"
    )

    # 34~40: 추가 정보 및 관리 필드
    collection = models.IntegerField(null=True, blank=True, verbose_name="게임 시리즈")
    parent_game = models.IntegerField(null=True, blank=True, verbose_name="게임 확장팩")
    cover = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="커버 이미지"
    )
    game_type = models.IntegerField(null=True, blank=True, verbose_name="게임 유형")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    like_count = models.IntegerField(default=0, verbose_name="좋아요 수")
    is_ban = models.BooleanField(default=False, verbose_name="블랙리스트")

    class Meta:
        db_table = "game_list"
        verbose_name = "게임 저장 테이블"
        indexes = [
            models.Index(
                fields=["status", "game_type", "-first_release_date", "-game_id"],
                name="idx_game_match_active",  # 명세서의 IDX_game_list_match_active
            ),
            models.Index(
                fields=["-first_release_date", "-game_id"],
                name="idx_game_release_desc",  # 명세서의 IDX_game_listl_release_desc
            ),
            models.Index(
                fields=["-rating", "-rating_count", "-game_id"],
                name="idx_game_rating_desc",  # 명세서의 IDX_game_list_rating_desc
            ),
        ]
