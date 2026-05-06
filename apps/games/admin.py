from django.contrib import admin

from apps.games.models import Game
from apps.match.models import MatchGamePreference


MATCH_VECTOR_DIM_LABELS = (
    "액션/격투",
    "어드벤처",
    "RPG/스토리",
    "전략/시뮬",
    "스포츠",
    "두뇌/퍼즐",
    "슈팅",
    "음악/리듬",
    "난이도",
    "톤",
    "그래픽",
    "템포",
    "사회성",
    "인기도",
)

MATCH_VECTOR_RADAR_LABELS = (
    "액션",
    "어드벤처",
    "RPG",
    "전략",
    "스포츠",
    "두뇌",
    "슈팅",
    "음악",
    "난이도",
    "톤",
    "그래픽",
    "템포",
    "사회성",
    "인기도",
)

MATCH_VECTOR_BIPOLAR_HINTS = {
    9: ("캐주얼", "하드코어"),   # 난이도
    10: ("밝음", "어두움"),     # 톤
    11: ("2D", "3D"),           # 그래픽
    12: ("정적", "동적"),       # 템포
    13: ("솔로", "멀티"),       # 사회성
}


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
        # 시스템/집계
        "game_id",
        "created_at",
        "like_count",
        # 원본 식별/설명 (배치 동기화 대상)
        "name",
        "slug",
        "summary",
        "storyline",
        # 원본 분류/상태
        "category",
        "status",
        "game_type",
        # 원본 출시/평점
        "first_release_date",
        "version_title",
        "rating",
        "rating_count",
        "aggregated_rating",
        "aggregated_rating_count",
        "total_rating",
        "total_rating_count",
        "follows",
        "hypes",
        # 원본 관계/미디어
        "collection",
        "parent_game",
        "cover",
        "screenshots",
        "videos",
        "websites",
        # 원본 JSON 메타
        "genres",
        "themes",
        "keywords",
        "game_modes",
        "player_perspectives",
        "multiplayer_modes",
        "involved_companies",
        "franchises",
        "remakes",
        "remasters",
        "expansions",
        "dlcs",
        "language_supports",
    )
    actions = (ban_games, unban_games)
    date_hierarchy = "created_at"
    list_per_page = 30
    empty_value_display = "-"
    change_form_template = "admin/games/game/change_form.html"

    fieldsets = (
        (
            "운영 제어",
            {
                "fields": (
                    "game_id",
                    "is_ban",
                    "ban_reason",
                    "created_at",
                )
            },
        ),
        (
            "노출 텍스트 (원문/번역)",
            {
                "fields": (
                    "name",
                    "name_ko",
                    "slug",
                    "summary",
                    "summary_ko",
                    "storyline",
                    "storyline_ko",
                )
            },
        ),
        (
            "미디어/외부 링크",
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
            "랭킹/추천 지표",
            {
                "fields": (
                    "first_release_date",
                    "rating",
                    "rating_count",
                    "aggregated_rating",
                    "aggregated_rating_count",
                    "total_rating",
                    "total_rating_count",
                    "follows",
                    "hypes",
                    "like_count",
                    "collection",
                    "parent_game",
                )
            },
        ),
        (
            "원본 JSON (참고용)",
            {
                "classes": ("collapse",),
                "fields": (
                    "category",
                    "status",
                    "game_type",
                    "genres",
                    "themes",
                    "keywords",
                    "game_modes",
                    "player_perspectives",
                    "multiplayer_modes",
                    "involved_companies",
                    "franchises",
                    "remakes",
                    "remasters",
                    "expansions",
                    "dlcs",
                    "language_supports",
                    "version_title",
                ),
            },
        ),
    )

    def _get_match_vector(self, obj) -> list[float] | None:
        pref = (
            MatchGamePreference.objects.filter(game_id=obj)
            .only("game_preference_vector")
            .first()
        )
        if pref is None or pref.game_preference_vector is None:
            return None

        try:
            values = [float(v) for v in list(pref.game_preference_vector)]
        except (TypeError, ValueError):
            return None

        if len(values) < len(MATCH_VECTOR_DIM_LABELS):
            values.extend([0.0] * (len(MATCH_VECTOR_DIM_LABELS) - len(values)))
        return values[: len(MATCH_VECTOR_DIM_LABELS)]

    def _clamp(self, value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(value, max_value))

    def _value_color(self, dim_index: int, value: float) -> str:
        if dim_index == 14:
            return "#a3e635"  # lime
        if dim_index <= 8:
            return "#7c6cff"  # purple
        if dim_index == 13:
            return "#22d3ee" if value < 0 else "#06b6d4"  # cyan
        return "#ff7a1a" if value >= 0 else "#22d3ee"  # orange / cyan

    def _build_vector_rows(self, values: list[float]) -> list[dict]:
        rows: list[dict] = []
        for idx, (label, raw_value) in enumerate(zip(MATCH_VECTOR_DIM_LABELS, values), start=1):
            color = self._value_color(idx, raw_value)

            if idx <= 8 or idx == 14:
                v = self._clamp(raw_value, 0.0, 1.0)
                rows.append(
                    {
                        "idx": idx,
                        "label": label,
                        "color": color,
                        "value_text": f"{v:.2f}",
                        "fill_left_pct": 0.0,
                        "fill_width_pct": round(v * 100.0, 2),
                        "is_bipolar": False,
                        "left_hint": "",
                        "right_hint": "",
                    }
                )
                continue

            v = self._clamp(raw_value, -1.0, 1.0)
            if abs(v) < 0.005:
                v = 0.0

            if v >= 0:
                fill_left = 50.0
                fill_width = v * 50.0
            else:
                fill_left = 50.0 - abs(v) * 50.0
                fill_width = abs(v) * 50.0

            left_hint, right_hint = MATCH_VECTOR_BIPOLAR_HINTS.get(idx, ("왼쪽", "오른쪽"))

            rows.append(
                {
                    "idx": idx,
                    "label": label,
                    "color": color,
                    "value_text": f"{v:.2f}",
                    "fill_left_pct": round(fill_left, 2),
                    "fill_width_pct": round(fill_width, 2),
                    "is_bipolar": True,
                    "left_hint": left_hint,
                    "right_hint": right_hint,
                }
            )

        return rows

    def render_change_form(
            self, request, context, add=False, change=False, form_url="", obj=None
    ):
        context = dict(context)
        chart_payload = None
        vector_rows: list[dict] = []

        if obj is not None:
            values = self._get_match_vector(obj)
            if values is not None:
                chart_payload = {
                    "game_id": obj.game_id,
                    "labels": list(MATCH_VECTOR_RADAR_LABELS),
                    "values": [round(v, 4) for v in values],
                }
                vector_rows = self._build_vector_rows(values)

        context["game_vector_chart"] = chart_payload
        context["game_vector_rows"] = vector_rows

        return super().render_change_form(
            request,
            context,
            add=add,
            change=change,
            form_url=form_url,
            obj=obj,
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
