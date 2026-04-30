from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
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
        "selected_game",
        "preview",
        "selected_by_summary",
        "updated_at_local",
    )
    list_display_links = ("api_genre_id", "genre_name")
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
            return ("admin_guide", "api_genre_id", "game", "image_url")
        return (
            "admin_guide",
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
        base = ("admin_guide",)
        if obj is None:
            return base
        return base + (
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

    @admin.display(description="운영 가이드")
    def admin_guide(self, obj=None) -> str:
        return mark_safe(
            "<ul style='margin:0; padding-left:18px;'>"
            "<li>장르별 대표 이미지는 <b>후보 이미지 선택</b>에서 직접 선택할 수 있습니다.</li>"
            "<li><b>장르 1~8 자동 채우기</b> 액션은 각 장르 후보 1순위를 게시본으로 반영합니다.</li>"
            "<li>이미지 비율이 맞지 않으면 같은 게임의 <b>스크린샷/아트워크</b>로 교체하세요.</li>"
            "</ul>"
        )

    @admin.display(description="장르명")
    def genre_name(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None:
            return "-"
        return API_GENRE_NAME_MAP.get(obj.api_genre_id, f"미정의({obj.api_genre_id})")

    @admin.display(description="선택 게임")
    def selected_game(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None or obj.game is None:
            return "-"
        return f"{obj.game_id} | {obj.game.name}"

    @admin.display(description="대표 이미지")
    def preview(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None or not obj.image_url:
            return "미설정"
        return format_html(
            '<img src="{}" style="max-height:140px; border-radius:8px;" />',
            obj.image_url,
        )

    @admin.display(description="선택자")
    def selected_by_summary(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None or obj.selected_by is None:
            return "-"
        return f"{obj.selected_by.login_id} ({obj.selected_by.nickname})"

    @admin.display(description="최종 수정 시각")
    def updated_at_local(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None or obj.updated_at is None:
            return "-"
        local_dt = timezone.localtime(obj.updated_at)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")

    @admin.display(description="후보 이미지 선택 (최대 5개 게임)")
    def candidate_options(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None:
            return "먼저 저장 후 확인하세요."

        candidates_by_genre = self._service().build_candidates(limit_per_genre=5)
        candidates = candidates_by_genre.get(obj.api_genre_id, [])
        if not candidates:
            return "현재 조건에서 후보를 찾지 못했습니다."

        blocks: list[str] = []
        for rank, candidate in enumerate(candidates, start=1):
            current = " (현재 선택)" if obj.game_id == candidate["game_id"] else ""
            images = candidate.get("images", [])

            if not images:
                image_lines = "이미지 없음"
            else:
                line_items: list[str] = []
                for img_idx, image in enumerate(images):
                    pick_url = f"../pick/{candidate['game_id']}/?img={img_idx}"
                    line_items.append(
                        str(
                            format_html(
                                "{}: <a href='{}' target='_blank'>미리보기</a> / <a href='{}'>이 이미지 선택</a>",
                                image["label"],
                                image["url"],
                                pick_url,
                            )
                        )
                    )
                image_lines = "<br>".join(line_items)

            block = format_html(
                "<b>{}위</b> | game_id={} | {} | 평점={} (표본={}){}<br>{}",
                rank,
                candidate["game_id"],
                candidate["name"],
                candidate["rating"],
                candidate["rating_count"],
                current,
                mark_safe(image_lines),
            )
            blocks.append(str(block))

        return format_html_join(
            mark_safe("<hr style='margin:8px 0'>"),
            "{}",
            ((mark_safe(v),) for v in blocks),
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: MatchGenreImagePublished,
        form,
        change: bool,
    ) -> None:
        if request.user.is_authenticated:
            obj.selected_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="장르 1~8 자동 채우기 (후보 1순위 게시)")
    def action_seed_or_refresh_with_top1(self, request: HttpRequest, queryset) -> None:
        updated, missing = self._service().seed_or_refresh(
            user=request.user if request.user.is_authenticated else None,
            limit_per_genre=5,
        )
        self.message_user(
            request,
            f"완료: {updated}개 장르 반영, 후보 부족/없음 {missing}개 장르",
            level=messages.SUCCESS,
        )

    def seed_view(self, request: HttpRequest) -> HttpResponseRedirect:
        updated, missing = self._service().seed_or_refresh(
            user=request.user if request.user.is_authenticated else None,
            limit_per_genre=5,
        )
        self.message_user(
            request,
            f"게시본 생성/갱신 완료: {updated}개 성공, {missing}개 미반영",
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
                reverse(
                    f"{self.admin_site.name}:match_matchgenreimagepublished_changelist"
                )
            )

        raw_img_idx = request.GET.get("img", "0")
        try:
            img_idx = int(raw_img_idx)
        except TypeError, ValueError:
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
