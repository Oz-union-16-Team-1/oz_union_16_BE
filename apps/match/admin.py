from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.match.constants import API_GENRE_NAME_MAP
from apps.match.models import MatchGenreImagePublished
from apps.match.services.genre_image_publish import MatchGenreImagePublishService


@admin.register(MatchGenreImagePublished)
class MatchGenreImagePublishedAdmin(admin.ModelAdmin):
    service_class = MatchGenreImagePublishService

    list_display = (
        "api_genre_id",
        "genre_name",
        "game",
        "preview",
        "selected_by",
        "updated_at",
    )
    list_filter = ("api_genre_id",)
    ordering = ("api_genre_id",)
    search_fields = ("game__name", "game__game_id")
    save_on_top = True
    list_per_page = 20
    raw_id_fields = ("game",)
    actions = ("action_seed_or_refresh_with_top1",)

    def _service(self) -> MatchGenreImagePublishService:
        return self.service_class()

    def get_fields(self, request: HttpRequest, obj=None):
        if obj is None:
            return ("api_genre_id", "game", "image_url")
        return (
            "api_genre_id",
            "genre_name",
            "game",
            "image_url",
            "preview",
            "candidate_options",
            "selected_by",
            "created_at",
            "updated_at",
        )

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        if obj is None:
            return ()
        return (
            "genre_name",
            "preview",
            "candidate_options",
            "selected_by",
            "created_at",
            "updated_at",
        )

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("game", "selected_by")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "seed/",
                self.admin_site.admin_view(self.seed_view),
                name="match_matchgenreimagepublished_seed",
            ),
            path(
                "<path:object_id>/pick/<int:game_id>/",
                self.admin_site.admin_view(self.pick_candidate_view),
                name="match_matchgenreimagepublished_pick_candidate",
            ),
        ]
        return custom_urls + urls

    @admin.display(description="장르명")
    def genre_name(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None:
            return "-"
        return API_GENRE_NAME_MAP.get(obj.api_genre_id, f"Unknown({obj.api_genre_id})")

    @admin.display(description="대표 이미지")
    def preview(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None or not obj.image_url:
            return "-"
        return format_html(
            '<img src="{}" style="max-height:140px;border-radius:8px;" />',
            obj.image_url,
        )

    @admin.display(description="후보 5개 (커버/스크린샷/아트워크)")
    def candidate_options(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None:
            return "먼저 저장한 뒤 후보를 선택하세요."

        candidates_by_genre = self._service().build_candidates(limit_per_genre=5)
        candidates = candidates_by_genre.get(obj.api_genre_id, [])
        if not candidates:
            return "후보 없음"

        lines: list[str] = []
        for rank, c in enumerate(candidates, start=1):
            current = " (현재선택)" if obj.game_id == c["game_id"] else ""
            images = c.get("images", [])

            if not images:
                links_html = "이미지 없음"
            else:
                parts: list[str] = []
                for idx, img in enumerate(images):
                    pick_url = f"../pick/{c['game_id']}/?img={idx}"
                    parts.append(
                        str(
                            format_html(
                                '<a href="{}" target="_blank">{}</a> / <a href="{}">선택</a>',
                                img["url"],
                                img["label"],
                                pick_url,
                            )
                        )
                    )
                links_html = " | ".join(parts)

            line = format_html(
                "{}. game_id={} | {} | rating={} (count={}){}<br>{}",
                rank,
                c["game_id"],
                c["name"],
                c["rating"],
                c["rating_count"],
                current,
                mark_safe(links_html),
            )
            lines.append(str(line))

        return format_html_join(
            mark_safe("<hr style='margin:8px 0'>"),
            "{}",
            ((mark_safe(v),) for v in lines),
        )

    def save_model(self, request: HttpRequest, obj: MatchGenreImagePublished, form, change: bool) -> None:
        if request.user.is_authenticated:
            obj.selected_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="장르 1~8 게시본 생성/보정 (후보 1순위 자동 반영)")
    def action_seed_or_refresh_with_top1(self, request: HttpRequest, queryset) -> None:
        updated, missing = self._service().seed_or_refresh(
            user=request.user if request.user.is_authenticated else None,
            limit_per_genre=5,
        )
        self.message_user(
            request,
            f"완료: {updated}개 장르 반영, 후보 없음 {missing}개 장르",
            level=messages.SUCCESS,
        )

    def seed_view(self, request: HttpRequest) -> HttpResponseRedirect:
        updated, missing = self._service().seed_or_refresh(
            user=request.user if request.user.is_authenticated else None,
            limit_per_genre=5,
        )
        self.message_user(
            request,
            f"완료: {updated}개 장르 게시본 생성/갱신, 후보 없음 {missing}개",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(
            reverse(f"{self.admin_site.name}:match_matchgenreimagepublished_changelist")
        )

    def pick_candidate_view(
        self,
        request: HttpRequest,
        object_id: str,
        game_id: int,
    ) -> HttpResponseRedirect:
        obj = self.get_object(request, object_id)
        if obj is None:
            self.message_user(request, "대상을 찾을 수 없습니다.", level=messages.ERROR)
            return HttpResponseRedirect(
                reverse(f"{self.admin_site.name}:match_matchgenreimagepublished_changelist")
            )

        raw_img_idx = request.GET.get("img", "0")
        try:
            img_idx = int(raw_img_idx)
        except (TypeError, ValueError):
            img_idx = 0

        ok, msg = self._service().pick_candidate_image(
            obj=obj,
            game_id=game_id,
            image_index=img_idx,
            user=request.user if request.user.is_authenticated else None,
            limit_per_genre=5,
        )
        self.message_user(
            request,
            msg,
            level=messages.SUCCESS if ok else messages.ERROR,
        )
        return HttpResponseRedirect(
            reverse(
                f"{self.admin_site.name}:match_matchgenreimagepublished_change",
                args=[obj.pk],
            )
        )
