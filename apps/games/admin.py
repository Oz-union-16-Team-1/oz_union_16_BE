import json

from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

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
        # 벡터 시각화
        "match_vector_dimensions",
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
            "매칭 벡터 정보",
            {
                "fields": (
                    "match_vector_dimensions",
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

    def render_change_form(
            self, request, context, add=False, change=False, form_url="", obj=None
    ):
        context = dict(context)
        chart_payload = None

        if obj is not None:
            values = self._get_match_vector(obj)
            if values is not None:
                chart_payload = {
                    "game_id": obj.game_id,
                    "labels": list(MATCH_VECTOR_RADAR_LABELS),
                    "values": [round(v, 4) for v in values],
                }

        context["game_vector_chart"] = chart_payload
        return super().render_change_form(
            request,
            context,
            add=add,
            change=change,
            form_url=form_url,
            obj=obj,
        )


    @admin.display(description="벡터 별자리 맵")
    def match_vector_radar(self, obj):
        values = self._get_match_vector(obj)
        if values is None:
            return "벡터 데이터 없음"

        labels_json = json.dumps(list(MATCH_VECTOR_RADAR_LABELS), ensure_ascii=False)
        values_json = json.dumps([round(v, 4) for v in values], ensure_ascii=False)

        return format_html(
            "<div style='max-width:860px;margin:0 auto;min-height:420px;display:flex;justify-content:center;align-items:center;'>"
            "<canvas class='js-game-vector-radar' "
            "data-game-id='{}' "
            "data-labels='{}' "
            "data-values='{}' "
            "style='width:100%;max-width:720px;height:420px;'></canvas>"
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

        rows_html = []
        for idx, (label, value) in enumerate(zip(MATCH_VECTOR_DIM_LABELS, values), start=1):
            color = self._value_color(idx, value)

            axis_hint = ""

            if idx <= 8 or idx == 14:
                track = self._render_unipolar_track(color, value)
                value_text = f"{self._clamp(value, 0.0, 1.0):.2f}"
            else:
                track = self._render_bipolar_track(color, value)
                vv = self._clamp(value, -1.0, 1.0)
                if abs(vv) < 0.005:
                    vv = 0.0
                value_text = f"{vv:.2f}"

                left_label, right_label = MATCH_VECTOR_BIPOLAR_HINTS.get(idx, ("왼쪽", "오른쪽"))
                axis_hint = (
                    "<div style='display:flex;justify-content:space-between;"
                    "margin-top:4px;font-size:12px;color:#6b7280;'>"
                    f"<span>← {left_label}</span>"
                    f"<span>{right_label} →</span>"
                    "</div>"
                )

            row = (
                "<div style='display:grid;grid-template-columns:160px 380px 72px;"
                "gap:14px;align-items:center;margin-bottom:10px;'>"
                f"<div style='font-weight:700;color:#9ca3af;font-size:15px;'>{label}</div>"
                f"<div>{track}{axis_hint}</div>"
                f"<div style='text-align:right;font-weight:800;color:{color};font-size:16px;'>{value_text}</div>"
                "</div>"
            )
            rows_html.append(row)

        if not rows_html:
            return "벡터 데이터 없음"

        return mark_safe(
            "<div style='max-width:860px;padding:8px 0 4px 0;'>"
            + "".join(rows_html)
            + "</div>"
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
