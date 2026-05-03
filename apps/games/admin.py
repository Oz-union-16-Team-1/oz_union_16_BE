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

    def _render_unipolar_track(self, color: str, value: float):
        width = self._clamp(value, 0.0, 1.0) * 100.0
        return format_html(
            "<div style='display:block;width:100%;height:12px;background:#1f2937;"
            "border:1px solid #334155;border-radius:9999px;overflow:hidden;'>"
            "<div style='display:block;height:100%;width:{}%;background:{};border-radius:9999px;'></div>"
            "</div>",
            f"{width:.2f}",
            color,
        )

    def _render_bipolar_track(self, color: str, value: float):
        v = self._clamp(value, -1.0, 1.0)
        if v >= 0:
            left = 50.0
            width = v * 50.0
        else:
            left = 50.0 - abs(v) * 50.0
            width = abs(v) * 50.0

        return format_html(
            "<div style='display:block;width:100%;height:12px;background:#1f2937;"
            "border:1px solid #334155;border-radius:9999px;overflow:hidden;position:relative;'>"
            "<div style='position:absolute;left:50%;top:0;bottom:0;width:1px;background:#475569;'></div>"
            "<div style='position:absolute;left:{}%;top:0;height:100%;width:{}%;background:{};border-radius:9999px;'></div>"
            "</div>",
            f"{left:.2f}",
            f"{width:.2f}",
            color,
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

            if idx <= 8 or idx == 14:
                track = self._render_unipolar_track(color, value)
                value_text = f"{self._clamp(value, 0.0, 1.0):.2f}"
            else:
                track = self._render_bipolar_track(color, value)
                vv = self._clamp(value, -1.0, 1.0)
                if abs(vv) < 0.005:
                    vv = 0.0
                value_text = f"{vv:.2f}"

            row = (
                "<div style='display:grid;grid-template-columns:160px 380px 72px;"
                "gap:14px;align-items:center;margin-bottom:10px;'>"
                f"<div style='font-weight:700;color:#9ca3af;font-size:15px;'>{label}</div>"
                f"<div>{track}</div>"
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
