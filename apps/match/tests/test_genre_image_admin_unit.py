from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.games.models import Game
from apps.match.admin import MatchGenreImagePublishedAdmin
from apps.match.models import MatchGenreImagePublished


class MatchGenreImageAdminUnitTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="genre_admin_unit_user",
            password="Pass1234!",
            name="관리자",
            nickname="admin_unit",
            gender="M",
        )
        cls.user.is_staff = True
        cls.user.is_superuser = True
        cls.user.save(update_fields=["is_staff", "is_superuser"])

        cls.game = Game.objects.create(
            game_id=6101, name="admin-game", slug="admin-game"
        )
        cls.obj = MatchGenreImagePublished.objects.create(
            api_genre_id=4,
            game=cls.game,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/admin.jpg",
            selected_by=cls.user,
        )

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.admin = MatchGenreImagePublishedAdmin(
            MatchGenreImagePublished,
            django_admin.site,
        )

    def _req(self, path: str = "/admin/match/matchgenreimagepublished/"):
        req = self.factory.get(path)
        req.user = self.user
        return req

    def test_get_fields_and_readonly_fields(self):
        req = self._req()
        self.assertIn("api_genre_id", self.admin.get_fields(req, obj=None))
        self.assertIn("candidate_options", self.admin.get_fields(req, obj=self.obj))

        ro_new = self.admin.get_readonly_fields(req, obj=None)
        ro_change = self.admin.get_readonly_fields(req, obj=self.obj)
        self.assertEqual(ro_new, ("admin_guide",))
        self.assertIn("preview", ro_change)

    def test_display_helpers(self):
        self.assertEqual(self.admin.genre_name(None), "-")
        self.assertIn("전략/시뮬", self.admin.genre_name(self.obj))

        self.assertEqual(self.admin.selected_game(None), "-")
        self.assertIn("admin-game", self.admin.selected_game(self.obj))

        self.assertEqual(self.admin.preview(None), "미설정")
        self.assertIn("<img", str(self.admin.preview(self.obj)))

        self.assertEqual(self.admin.selected_by_summary(None), "-")
        self.assertIn(self.user.login_id, self.admin.selected_by_summary(self.obj))

        self.assertEqual(self.admin.updated_at_local(None), "-")
        self.assertTrue(self.admin.updated_at_local(self.obj))

        guide = str(self.admin.admin_guide(self.obj))
        self.assertIn("장르별 대표 이미지는", guide)
        self.assertIn("장르 1~8 자동 채우기", guide)

    def test_get_queryset_executes(self):
        req = self._req()
        qs = self.admin.get_queryset(req)
        self.assertTrue(qs.filter(pk=self.obj.pk).exists())

    def test_candidate_options_branches(self):
        # obj=None
        self.assertIn("먼저 저장", self.admin.candidate_options(None))

        # 후보 없음
        with patch.object(self.admin, "_service") as mock_service:
            mock_service.return_value.build_candidates.return_value = {4: []}
            html = str(self.admin.candidate_options(self.obj))
            self.assertIn("후보를 찾지 못했습니다", html)

        # 후보 있음 (이미지/현재선택/링크 렌더)
        candidate = {
            "game_id": self.obj.game_id,
            "name": "admin-game",
            "rating": 99.1,
            "rating_count": 321,
            "images": [
                {
                    "url": "https://images.igdb.com/igdb/image/upload/t_1080p/co1.jpg",
                    "source": "cover",
                    "label": "대표 커버",
                },
                {
                    "url": "https://images.igdb.com/igdb/image/upload/t_1080p/sc1.jpg",
                    "source": "screenshot",
                    "label": "스크린샷 #1",
                },
            ],
        }
        with patch.object(self.admin, "_service") as mock_service:
            mock_service.return_value.build_candidates.return_value = {4: [candidate]}
            html = str(self.admin.candidate_options(self.obj))
            self.assertIn("현재 선택", html)
            self.assertIn("대표 커버", html)
            self.assertIn("스크린샷 #1", html)
            self.assertIn("이 이미지 선택", html)

        # 이미지 없음 분기
        candidate_no_img = {
            "game_id": 9999,
            "name": "no-image",
            "rating": 77.7,
            "rating_count": 22,
            "images": [],
        }
        with patch.object(self.admin, "_service") as mock_service:
            mock_service.return_value.build_candidates.return_value = {
                4: [candidate_no_img]
            }
            html = str(self.admin.candidate_options(self.obj))
            self.assertIn("이미지 없음", html)

    def test_save_model_sets_selected_by(self):
        req = self._req()
        obj = MatchGenreImagePublished(
            api_genre_id=8,
            game=self.game,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/new.jpg",
        )
        self.admin.save_model(req, obj, form=Mock(), change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.selected_by_id, self.user.id)

    def test_action_seed_and_seed_view(self):
        req = self._req()

        with (
            patch.object(self.admin, "_service") as mock_service,
            patch.object(self.admin, "message_user") as mock_msg,
        ):
            mock_service.return_value.seed_or_refresh.return_value = (8, 0)
            self.admin.action_seed_or_refresh_with_top1(req, queryset=None)
            self.assertTrue(mock_msg.called)

        with (
            patch.object(self.admin, "_service") as mock_service,
            patch.object(self.admin, "message_user") as mock_msg,
        ):
            mock_service.return_value.seed_or_refresh.return_value = (7, 1)
            resp = self.admin.seed_view(req)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(mock_msg.called)

    def test_pick_candidate_view_paths(self):
        req = self._req()

        # 대상 없음
        with (
            patch.object(self.admin, "get_object", return_value=None),
            patch.object(self.admin, "message_user") as mock_msg,
        ):
            resp = self.admin.pick_candidate_view(req, object_id="999999", game_id=1)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(mock_msg.called)

        # 대상 있음 + img 파라미터 비정상 -> 0 보정 + 성공
        req_bad_img = self._req(
            f"/admin/match/matchgenreimagepublished/{self.obj.pk}/pick/{self.game.game_id}/?img=abc"
        )
        req_bad_img.GET = req_bad_img.GET.copy()
        req_bad_img.GET["img"] = "abc"

        with (
            patch.object(self.admin, "get_object", return_value=self.obj),
            patch.object(self.admin, "_service") as mock_service,
            patch.object(self.admin, "message_user") as mock_msg,
        ):
            mock_service.return_value.pick_candidate_image.return_value = (True, "ok")
            resp = self.admin.pick_candidate_view(
                req_bad_img,
                object_id=str(self.obj.pk),
                game_id=self.game.game_id,
            )
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(mock_msg.called)
