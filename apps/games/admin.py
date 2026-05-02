import json

from django.contrib import admin
from django.utils.html import format_html

from apps.games.models import Game
from apps.match.models import MatchGamePreference


MATCH_VECTOR_DIM_LABELS = (
    "액션/격투",
    "어드벤처/플랫폼",
    "RPG/스토리",
    "전략/시뮬",
    "스포츠/레이싱",
    "두뇌/퍼즐",
    "슈팅",
    "음악/리듬",
    "난이도(캐주얼↔하드코어)",
    "톤(밝음↔어두움)",
    "그래픽(2D↔3D)",
    "템포(정적↔동적)",
    "사회성(솔로↔멀티)",
    "인기도 참조",
)


class GameBlacklist(Game):
    class Meta:
        proxy = True
        verbose_name = "게임 블랙리스트"
        verbose_name_plural = "게임 블랙리스트"


@admin.action(description="선택한 게임 블랙리스트 등록")
def ban_games(modeladmin, request, queryset):
    queryset.update(is_ban=True)


@admin.action(description="선택한 게임 블랙리스트 해제")
def unban_games(modeladmin, request, queryset):
    queryset.update(is_ban=False, ban_reason="")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "game_id",
        "name",
        "name_ko",
        "is_ban_display",
        "ban_reason",
        "rating",
        "like_count",
        "created_at",
    )

    ordering = ("-created_at",)
    search_fields = ("game_id", "name", "name_ko")
    list_filter = ("is_ban", "created_at")
    readonly_fields = (
        "game_id",
        "created_at",
        "match_vector_radar",
        "match_vector_dimensions",
    )
    actions = (ban_games, unban_games)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    fieldsets = (
        (
            "기본 정보",
            {
                "fields": (
                    "game_id",
                    "name",
                    "name_ko",
                    "slug",
                    "summary",
                    "storyline",
                    "rating",
                    "like_count",
                    "is_ban",
                    "ban_reason",
                    "created_at",
                )
            },
        ),
        (
            "분류 정보",
            {
                "fields": (
                    "category",
                    "status",
                    "game_type",
                    "genres",
                    "themes",
                    "keywords",
                )
            },
        ),
        (
            "이미지/영상/링크",
            {
                "fields": (
                    "cover",
                    "screenshots",
                    "videos",
                    "websites",
                )
            },
        ),
        (
            "출시/평점 정보",
            {
                "fields": (
                    "first_release_date",
                    "rating_count",
                    "aggregated_rating",
                    "aggregated_rating_count",
                    "total_rating",
                    "total_rating_count",
                    "follows",
                    "hypes",
                )
            },
        ),
        (
            "매칭 벡터 정보",
            {
                "fields": (
                    "match_vector_radar",
                    "match_vector_dimensions",
                )
            },
        ),
    )

    class Media:
        js = (
            "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js",
            "games_admin/game_vector_chart.js",
        )

    def _get_match_vector(self, obj) -> list[float] | None:
        pref = (
            MatchGamePreference.objects.filter(game_id=obj)
            .only("game_preference_vector")
            .first()
        )
        if pref is None or pref.game_preference_vector is None:
            return None

        raw = pref.game_preference_vector
        try:
            values = [float(v) for v in list(raw)]
        except TypeError:
            return None

        if len(values) < len(MATCH_VECTOR_DIM_LABELS):
            values.extend([0.0] * (len(MATCH_VECTOR_DIM_LABELS) - len(values)))
        return values[: len(MATCH_VECTOR_DIM_LABELS)]

    @admin.display(description="벡터 별자리 맵")
    def match_vector_radar(self, obj):
        values = self._get_match_vector(obj)
        if values is None:
            return "벡터 데이터 없음"

        labels_json = json.dumps(list(MATCH_VECTOR_DIM_LABELS), ensure_ascii=False)
        values_json = json.dumps([round(v, 4) for v in values], ensure_ascii=False)

        return format_html(
            "<div style='max-width: 860px;'>"
            "<canvas class='js-game-vector-radar' "
            "data-game-id='{}' "
            "data-labels='{}' "
            "data-values='{}' "
            "height='320'></canvas>"
            "</div>",
            obj.game_id,
            labels_json,
            values_json,
        )

    @admin.display(description="차원별 벡터값")
    def match_vector_dimensions(self, obj):
        values = self._get_match_vector(obj)
        if values is None:
            return "벡터 데이터 없음"

        lines = []
        for idx, label in enumerate(MATCH_VECTOR_DIM_LABELS, start=1):
            lines.append(f"{idx:02d}. {label}: {values[idx - 1]:.4f}")

        return format_html(
            "<pre style='white-space: pre-wrap; margin: 0;'>{}</pre>",
            "\n".join(lines),
        )

    @admin.display(boolean=True, description="블랙리스트", ordering="is_ban")
    def is_ban_display(self, obj):
        return obj.is_ban


@admin.register(GameBlacklist)
class GameBlacklistAdmin(admin.ModelAdmin):
    list_display = (
        "game_id",
        "name",
        "name_ko",
        "ban_reason",
        "created_at",
    )

    ordering = ("-created_at",)
    search_fields = ("game_id", "name", "name_ko")
    list_filter = ("created_at",)
    readonly_fields = ("game_id", "name", "name_ko", "created_at")
    actions = (unban_games,)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"

    fieldsets = (
        (
            "블랙리스트 정보",
            {
                "fields": (
                    "game_id",
                    "name",
                    "name_ko",
                    "ban_reason",
                    "created_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_ban=True)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
