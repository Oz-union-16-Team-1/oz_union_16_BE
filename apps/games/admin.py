from urllib.parse import urlparse

from django.contrib import admin
from django.utils.html import format_html, format_html_join

from apps.games.models import Game
from apps.match.constants import IGDB_GENRE_NAME_MAP
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
    9: ("캐주얼", "하드코어"),  # 난이도
    10: ("밝음", "어두움"),  # 톤
    11: ("2D", "3D"),  # 그래픽
    12: ("정적", "동적"),  # 템포
    13: ("솔로", "멀티"),  # 사회성
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


class MatchGenreFilter(admin.SimpleListFilter):
    title = "매칭 장르"
    parameter_name = "match_genre"

    def lookups(self, request, model_admin):
        return tuple(
            (str(genre_id), IGDB_GENRE_NAME_MAP.get(genre_id, str(genre_id)))
            for genre_id in range(1, 15)
        )

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset

        try:
            genre_id = int(value)
        except TypeError, ValueError:
            return queryset

        return queryset.filter(genre_maps__igdb_genre_id=genre_id).distinct()


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
    list_filter = (MatchGenreFilter, "is_ban", "created_at")
    readonly_fields = (
        # 시스템/집계
        "game_id",
        "created_at",
        "like_count",
        # 원본 식별/설명 (배치 동기화 대상)
        "name",
        "slug",
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
        "media_cover_links",
        "media_screenshot_links",
        "media_video_links",
        "media_website_links",
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
                    "media_cover_links",
                    "media_screenshot_links",
                    "media_video_links",
                    "media_website_links",
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
                    "cover",
                    "screenshots",
                    "videos",
                    "websites",
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
        except TypeError, ValueError:
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
        for idx, (label, raw_value) in enumerate(
            zip(MATCH_VECTOR_DIM_LABELS, values), start=1
        ):
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

            left_hint, right_hint = MATCH_VECTOR_BIPOLAR_HINTS.get(
                idx, ("왼쪽", "오른쪽")
            )

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

    def _to_igdb_image_url(self, value: object, size: str = "t_1080p") -> str | None:
        if not isinstance(value, str):
            return None

        raw = value.strip()
        if not raw:
            return None

        if raw.startswith("//"):
            return f"https:{raw}".replace("t_thumb", size)

        if raw.startswith("http://") or raw.startswith("https://"):
            return raw.replace("t_thumb", size)

        return f"https://images.igdb.com/igdb/image/upload/{size}/{raw}.jpg"

    def _normalize_external_url(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None

        raw = value.strip()
        if not raw:
            return None

        if raw.startswith("//"):
            return f"https:{raw}"
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        if raw.startswith("www."):
            return f"https://{raw}"
        if "://" not in raw and "." in raw and " " not in raw:
            return f"https://{raw}"
        return None

    def _extract_image_urls(self, raw_images: object) -> list[str]:
        urls: list[str] = []
        if not isinstance(raw_images, list):
            return urls

        for item in raw_images:
            url: str | None = None

            if isinstance(item, str):
                url = self._to_igdb_image_url(item)
            elif isinstance(item, dict):
                direct_url = item.get("url")
                image_id = item.get("image_id")
                url = self._to_igdb_image_url(direct_url) or self._to_igdb_image_url(
                    image_id
                )

            if url and url not in urls:
                urls.append(url)

        return urls

    def _extract_video_urls(self, raw_videos: object) -> list[str]:
        urls: list[str] = []
        if not isinstance(raw_videos, list):
            return urls

        for item in raw_videos:
            video_value: str | None = None
            if isinstance(item, str) and item.strip():
                video_value = item.strip()
            elif isinstance(item, dict):
                for key in ("video_id", "url", "id"):
                    raw = item.get(key)
                    if isinstance(raw, str) and raw.strip():
                        video_value = raw.strip()
                        break

            if not video_value:
                continue

            normalized = self._normalize_external_url(video_value)
            url = normalized or f"https://www.youtube.com/watch?v={video_value}"
            if url not in urls:
                urls.append(url)

        return urls

    def _extract_website_urls(self, raw_websites: object) -> list[str]:
        urls: list[str] = []
        if not isinstance(raw_websites, list):
            return urls

        for item in raw_websites:
            raw_url: object = None
            if isinstance(item, dict):
                raw_url = item.get("url")
            else:
                raw_url = item

            url = self._normalize_external_url(raw_url)
            if url and url not in urls:
                urls.append(url)

        return urls

    def _render_link_list(self, urls: list[str], *, empty_message: str):
        if not urls:
            return empty_message

        return format_html(
            "<div style='display:flex;flex-direction:column;gap:6px;'>" "{}" "</div>",
            format_html_join(
                "",
                "<a href='{}' target='_blank' rel='noopener noreferrer'>{}</a>",
                ((url, url) for url in urls),
            ),
        )

    @admin.display(description="커버 이미지 URL")
    def media_cover_links(self, obj: Game):
        url = self._to_igdb_image_url(obj.cover)
        return self._render_link_list(
            [url] if isinstance(url, str) else [],
            empty_message="커버 이미지 없음",
        )

    @admin.display(description="스크린샷 URL 목록")
    def media_screenshot_links(self, obj: Game):
        return self._render_link_list(
            self._extract_image_urls(obj.screenshots),
            empty_message="스크린샷 없음",
        )

    @admin.display(description="트레일러 URL 목록")
    def media_video_links(self, obj: Game):
        return self._render_link_list(
            self._extract_video_urls(obj.videos),
            empty_message="트레일러 없음",
        )

    @admin.display(description="외부 링크 목록")
    def media_website_links(self, obj: Game):
        website_urls = self._extract_website_urls(obj.websites)
        if not website_urls:
            return "외부 링크 없음"

        return format_html(
            "<div style='display:flex;flex-direction:column;gap:6px;'>" "{}" "</div>",
            format_html_join(
                "",
                "<a href='{0}' target='_blank' rel='noopener noreferrer'>{1}</a>",
                ((url, urlparse(url).netloc or url) for url in website_urls),
            ),
        )

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
