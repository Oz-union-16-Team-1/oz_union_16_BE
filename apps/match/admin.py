from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import admin, messages
from django.db.models import FloatField, IntegerField, Q
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.core.igdb import igdb_client
from apps.games.models import Game
from apps.match.constants import (
    API_GENRE_NAME_MAP,
    API_TO_IGDB_IMAGE_GENRE_MAP,
    GENRE_PRIORITY,
    MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES,
    MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS,
    MATCH_GENRE_IMAGE_MIN_RATING,
    MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
    MATCH_GENRE_IMAGE_MONTHLY_END_MONTH,
    MATCH_GENRE_IMAGE_MONTHLY_START_DAYS,
    MATCH_GENRE_IMAGE_REQUIRED_STATUS,
    MATCH_GENRE_IMAGE_YEARLY_END,
    MATCH_GENRE_IMAGE_YEARLY_START,
)
from apps.match.models import MatchGenreImagePublished


def _normalize_image_url(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    url = raw.strip()
    if not url:
        return None

    if url.startswith("//"):
        url = f"https:{url}"

    if not url.startswith("http://") and not url.startswith("https://"):
        # image_id만 넘어온 경우
        url = f"https://images.igdb.com/igdb/image/upload/t_1080p/{url}.jpg"

    return url.replace("t_thumb", "t_1080p")


def _image_id_to_url(image_id: str) -> str:
    return f"https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg"


@admin.register(MatchGenreImagePublished)
class MatchGenreImagePublishedAdmin(admin.ModelAdmin):
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
            '<img src="{}" style="max-height:140px; border-radius:8px;" />',
            obj.image_url,
        )

    @admin.display(description="후보 5개 (커버/스크린샷/아트워크 선택)")
    def candidate_options(self, obj: MatchGenreImagePublished | None) -> str:
        if obj is None:
            return "먼저 저장한 뒤 후보를 선택하세요."

        candidates_by_genre = self._build_candidates_by_genre(limit_per_genre=5)
        candidates = candidates_by_genre.get(obj.api_genre_id, [])
        if not candidates:
            return "후보 없음"

        lines: list[str] = []
        for rank, c in enumerate(candidates, start=1):
            current = " (현재선택)" if obj.game_id == c["game_id"] else ""
            urls = c.get("image_urls", [])

            if not urls:
                links_html = "이미지 없음"
            else:
                link_items: list[str] = []
                for img_idx, image_url in enumerate(urls, start=1):
                    pick_url = f"../pick/{c['game_id']}/?img={img_idx-1}"
                    link_items.append(
                        str(
                            format_html(
                                '<a href="{}" target="_blank">img{}</a> / <a href="{}">선택</a>',
                                image_url,
                                img_idx,
                                pick_url,
                            )
                        )
                    )
                links_html = " | ".join(link_items)

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

        return format_html_join(mark_safe("<hr style='margin:8px 0'>"), "{}", ((mark_safe(v),) for v in lines))

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

    @admin.action(description="장르 1~8 게시본 생성/보정 (후보 1순위 자동 반영)")
    def action_seed_or_refresh_with_top1(self, request: HttpRequest, queryset) -> None:
        self._seed_or_refresh(request)

    def seed_view(self, request: HttpRequest) -> HttpResponseRedirect:
        self._seed_or_refresh(request)
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

        candidates_by_genre = self._build_candidates_by_genre(limit_per_genre=5)
        candidate_map = {
            c["game_id"]: c for c in candidates_by_genre.get(obj.api_genre_id, [])
        }
        picked = candidate_map.get(game_id)
        if picked is None:
            self.message_user(
                request,
                "선택한 게임은 현재 후보 5개에 없습니다. 새로고침 후 다시 선택하세요.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse(
                    f"{self.admin_site.name}:match_matchgenreimagepublished_change",
                    args=[obj.pk],
                )
            )

        urls = picked.get("image_urls", [])
        if not urls:
            self.message_user(request, "선택 가능한 이미지가 없습니다.", level=messages.ERROR)
            return HttpResponseRedirect(
                reverse(
                    f"{self.admin_site.name}:match_matchgenreimagepublished_change",
                    args=[obj.pk],
                )
            )

        raw_img_idx = request.GET.get("img", "0")
        try:
            img_idx = int(raw_img_idx)
        except (TypeError, ValueError):
            img_idx = 0
        if img_idx < 0 or img_idx >= len(urls):
            img_idx = 0

        obj.game_id = picked["game_id"]
        obj.image_url = urls[img_idx]
        if request.user.is_authenticated:
            obj.selected_by = request.user
        obj.save(update_fields=["game", "image_url", "selected_by", "updated_at"])

        self.message_user(
            request,
            f"장르 {obj.api_genre_id} 게시본을 game_id={picked['game_id']} 이미지 #{img_idx+1}로 반영했습니다.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(
            reverse(
                f"{self.admin_site.name}:match_matchgenreimagepublished_change",
                args=[obj.pk],
            )
        )

    def _seed_or_refresh(self, request: HttpRequest) -> None:
        candidates_by_genre = self._build_candidates_by_genre(limit_per_genre=5)
        updated = 0
        missing = 0

        for genre_id in range(1, 9):
            candidates = candidates_by_genre.get(genre_id, [])
            if not candidates:
                missing += 1
                continue

            top1 = candidates[0]
            urls = top1.get("image_urls", [])
            if not urls:
                missing += 1
                continue

            MatchGenreImagePublished.objects.update_or_create(
                api_genre_id=genre_id,
                defaults={
                    "game_id": top1["game_id"],  # FK attname
                    "image_url": urls[0],
                    "selected_by": request.user if request.user.is_authenticated else None,
                },
            )
            updated += 1

        self.message_user(
            request,
            f"완료: {updated}개 장르 게시본 반영, 후보 없음 {missing}개 장르",
            level=messages.SUCCESS,
        )

    def _build_cutoff_days(self) -> list[int]:
        monthly = [
            MATCH_GENRE_IMAGE_MONTHLY_START_DAYS * i
            for i in range(1, MATCH_GENRE_IMAGE_MONTHLY_END_MONTH + 1)
        ]
        yearly = [365 * y for y in range(MATCH_GENRE_IMAGE_YEARLY_START, MATCH_GENRE_IMAGE_YEARLY_END + 1)]
        return monthly + yearly

    def _build_candidates_by_genre(self, limit_per_genre: int = 5) -> dict[int, list[dict[str, Any]]]:
        ranked_by_genre: dict[int, list[dict[str, Any]]] = {}
        for genre_id in range(1, 9):
            ranked_by_genre[genre_id] = self._fetch_ranked_candidates_for_genre(
                api_genre_id=genre_id,
                scan_limit=2000,
            )

        now_ts = int(timezone.now().timestamp())
        selected: dict[int, list[dict[str, Any]]] | None = None

        for days in self._build_cutoff_days():
            cutoff_ts = now_ts - (days * 24 * 60 * 60)
            filtered_by_genre: dict[int, list[dict[str, Any]]] = {}
            for genre_id, rows in ranked_by_genre.items():
                filtered_by_genre[genre_id] = [
                    r for r in rows if int(r.get("release_ts", 0)) >= cutoff_ts
                ]

            picked = self._assign_with_priority(
                ranked_by_genre=filtered_by_genre,
                limit_per_genre=limit_per_genre,
            )

            # 각 장르 최소 1개 이상 확보되면 해당 cutoff 채택
            if all(len(picked.get(gid, [])) >= 1 for gid in range(1, 9)):
                selected = picked
                break

        if selected is None:
            selected = self._assign_with_priority(
                ranked_by_genre=ranked_by_genre,
                limit_per_genre=limit_per_genre,
            )

        self._attach_artworks(selected)
        return selected

    def _assign_with_priority(
        self,
        ranked_by_genre: dict[int, list[dict[str, Any]]],
        limit_per_genre: int,
    ) -> dict[int, list[dict[str, Any]]]:
        selected_by_genre: dict[int, list[dict[str, Any]]] = {gid: [] for gid in range(1, 9)}
        used_game_ids: set[int] = set()

        for genre_id in GENRE_PRIORITY:
            ranked = ranked_by_genre.get(genre_id, [])
            chosen: list[dict[str, Any]] = []
            chosen_ids: set[int] = set()

            # 1차: 장르 간 중복 제거
            for c in ranked:
                gid = int(c["game_id"])
                if gid in used_game_ids:
                    continue
                chosen.append(c)
                chosen_ids.add(gid)
                if len(chosen) >= limit_per_genre:
                    break

            # 2차: 그래도 부족하면 해당 장르 내부 중복허용 보충
            if len(chosen) < limit_per_genre:
                for c in ranked:
                    gid = int(c["game_id"])
                    if gid in chosen_ids:
                        continue
                    chosen.append(c)
                    chosen_ids.add(gid)
                    if len(chosen) >= limit_per_genre:
                        break

            selected_by_genre[genre_id] = chosen[:limit_per_genre]
            used_game_ids.update(chosen_ids)

        return selected_by_genre

    def _fetch_ranked_candidates_for_genre(
        self,
        api_genre_id: int,
        scan_limit: int = 2000,
    ) -> list[dict[str, Any]]:
        igdb_genre_ids = API_TO_IGDB_IMAGE_GENRE_MAP.get(api_genre_id, [])
        if not igdb_genre_ids:
            return []

        genre_q = Q()
        for gid in igdb_genre_ids:
            genre_q |= Q(genres__contains=[gid])
        if not genre_q.children:
            return []

        cutoff_dt = timezone.now() - timedelta(days=MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS * 365)

        rows = (
            Game.objects.filter(genre_q, is_ban=False)
            .filter(first_release_date__isnull=False, first_release_date__gte=cutoff_dt)
            .filter(Q(category__isnull=True) | Q(category__in=MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES))
            .filter(Q(status__isnull=True) | Q(status=MATCH_GENRE_IMAGE_REQUIRED_STATUS))
            .annotate(
                score_rating=Coalesce("total_rating", "rating", output_field=FloatField()),
                score_count=Coalesce("total_rating_count", "rating_count", output_field=IntegerField()),
            )
            .filter(
                score_rating__gte=MATCH_GENRE_IMAGE_MIN_RATING,
                score_count__gte=MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
            )
            .values(
                "game_id",
                "name",
                "cover",
                "screenshots",
                "score_rating",
                "score_count",
                "first_release_date",
            )
            .order_by(
                "-first_release_date",
                "-score_rating",
                "-score_count",
                "-game_id",
            )[:scan_limit]
        )

        out: list[dict[str, Any]] = []
        for row in rows:
            image_urls: list[str] = []

            cover_url = _normalize_image_url(row.get("cover"))
            if cover_url:
                image_urls.append(cover_url)

            image_urls.extend(self._extract_urls_from_media(row.get("screenshots")))
            image_urls = self._merge_unique_urls(image_urls)
            if not image_urls:
                continue

            release_dt = row.get("first_release_date")
            release_ts = int(release_dt.timestamp()) if release_dt is not None else 0

            out.append(
                {
                    "game_id": int(row["game_id"]),
                    "name": str(row.get("name") or ""),
                    "rating": round(float(row.get("score_rating") or 0.0), 2),
                    "rating_count": int(row.get("score_count") or 0),
                    "release_ts": release_ts,
                    "image_urls": image_urls,
                }
            )

        return out

    def _attach_artworks(self, selected_by_genre: dict[int, list[dict[str, Any]]]) -> None:
        game_ids: list[int] = []
        for candidates in selected_by_genre.values():
            for c in candidates:
                game_ids.append(int(c["game_id"]))

        artwork_map = self._fetch_artwork_urls_map(game_ids)
        if not artwork_map:
            return

        for candidates in selected_by_genre.values():
            for c in candidates:
                gid = int(c["game_id"])
                merged = self._merge_unique_urls(c.get("image_urls", []) + artwork_map.get(gid, []))
                c["image_urls"] = merged

    def _fetch_artwork_urls_map(self, game_ids: list[int]) -> dict[int, list[str]]:
        unique_ids = sorted(set(game_ids))
        if not unique_ids:
            return {}

        result: dict[int, list[str]] = {}
        chunk_size = 200

        for i in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[i : i + chunk_size]
            ids_str = ",".join(str(v) for v in chunk)
            query = (
                "fields id, artworks.image_id, artworks.url; "
                f"where id = ({ids_str}); "
                f"limit {len(chunk)};"
            )

            try:
                rows = igdb_client.query_games_raw(query) or []
            except Exception:
                rows = []

            if not isinstance(rows, list):
                continue

            for row in rows:
                try:
                    gid = int(row.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if gid <= 0:
                    continue

                urls = self._extract_urls_from_media(row.get("artworks"))
                if not urls:
                    continue

                prev = result.get(gid, [])
                result[gid] = self._merge_unique_urls(prev + urls)

        return result

    def _extract_urls_from_media(self, raw: Any) -> list[str]:
        urls: list[str] = []
        if not isinstance(raw, list):
            return urls

        for item in raw:
            if isinstance(item, dict):
                image_id = item.get("image_id")
                if isinstance(image_id, str) and image_id.strip():
                    urls.append(_image_id_to_url(image_id.strip()))

                maybe_url = _normalize_image_url(item.get("url"))
                if maybe_url:
                    urls.append(maybe_url)
                continue

            if isinstance(item, str):
                normalized = _normalize_image_url(item)
                if normalized:
                    urls.append(normalized)
                elif item.strip():
                    urls.append(_image_id_to_url(item.strip()))

        return self._merge_unique_urls(urls)

    def _merge_unique_urls(self, urls: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = _normalize_image_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out
