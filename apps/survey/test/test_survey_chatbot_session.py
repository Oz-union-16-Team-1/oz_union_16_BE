import uuid
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.survey.choices import (
    ChatbotModelChoices,
    SurveyRoleChoices,
    SurveyStatusChoices,
)
from apps.survey.models import (
    SurveyChatbotMessage,
    SurveyChatbotSession,
    SurveyResults,
)
from apps.survey.services.survey_chatbot_session import (
    SurveyChatbotSessionService,
    SurveyQuestionGenerationUnavailable,
)
from apps.users.models import User

TEST_FIRST_QUESTION = (
    "최근 가장 오래 몰입했던 게임에서 어떤 요소가 좋았는지 알려주세요."
)


def create_user(**kwargs) -> User:
    defaults = {
        "login_id": f"survey_{uuid.uuid4().hex[:8]}",
        "password": "testpassword123",
        "name": "설문유저",
        "nickname": f"survey_nick_{uuid.uuid4().hex[:8]}",
        "gender": "M",
    }
    defaults.update(kwargs)
    password = defaults.pop("password")
    user = User(**defaults)
    user.set_password(password)
    user.save()
    return user


class SurveyChatbotSessionCreateAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("survey-chatbot-session-create")

    def setUp(self) -> None:
        self.client = APIClient()
        self.user = create_user()
        self.question_patcher = patch(
            "apps.survey.services.survey_chatbot_session."
            "SurveyChatbotSessionService.generate_question_with_llm",
            return_value=TEST_FIRST_QUESTION,
        )
        self.question_patcher.start()
        self.addCleanup(self.question_patcher.stop)

    def authenticate(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_authentication_required(self) -> None:
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_session_success(self) -> None:
        self.authenticate()

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], SurveyStatusChoices.OPEN)
        self.assertFalse(response.data["recommendation_ready"])
        self.assertIsNotNone(response.data["session_id"])
        self.assertTrue(response.data["ai_question"])
        self.assertEqual(
            response.data["progress"],
            {
                "current_step": 0,
                "total_steps": None,
                "completion_rate": None,
            },
        )

        session = SurveyChatbotSession.objects.get(user=self.user)
        self.assertEqual(str(session.id), str(response.data["session_id"]))
        self.assertEqual(session.using_model, ChatbotModelChoices.GEMINI_2_5_FLASH)

        message = SurveyChatbotMessage.objects.get(session=session)
        self.assertEqual(message.role, SurveyRoleChoices.AI)
        self.assertEqual(message.sequence, 1)
        self.assertEqual(message.message, response.data["ai_question"])

    def test_create_session_without_reset_reuses_existing_session(self) -> None:
        self.authenticate()
        first_response = self.client.post(self.url, {}, format="json")

        second_response = self.client.post(self.url, {"is_reset": False}, format="json")

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            second_response.data["session_id"], first_response.data["session_id"]
        )
        self.assertEqual(
            second_response.data["ai_question"], first_response.data["ai_question"]
        )
        self.assertEqual(SurveyChatbotSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SurveyChatbotMessage.objects.count(), 1)

    def test_create_session_with_reset_creates_new_session_and_clears_previous_data(
        self,
    ) -> None:
        self.authenticate()
        first_response = self.client.post(self.url, {}, format="json")
        old_session = SurveyChatbotSession.objects.get(user=self.user)
        SurveyChatbotMessage.objects.create(
            session=old_session,
            role=SurveyRoleChoices.USER,
            sequence=2,
            message="액션 게임을 좋아합니다.",
        )
        SurveyResults.objects.create(
            chatbot_session=old_session,
            user=self.user,
            survey_answer="액션 게임 선호",
        )
        old_session.status = SurveyStatusChoices.IN_PROGRESS
        old_session.target_question_count = 3
        old_session.save(update_fields=["status", "target_question_count"])

        reset_response = self.client.post(self.url, {"is_reset": True}, format="json")

        self.assertEqual(reset_response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(
            reset_response.data["session_id"], first_response.data["session_id"]
        )
        self.assertEqual(reset_response.data["status"], SurveyStatusChoices.OPEN)
        self.assertEqual(
            reset_response.data["progress"],
            {
                "current_step": 0,
                "total_steps": None,
                "completion_rate": None,
            },
        )

        self.assertFalse(
            SurveyChatbotSession.objects.filter(id=old_session.id).exists()
        )
        self.assertFalse(
            SurveyResults.objects.filter(chatbot_session=old_session).exists()
        )
        new_session = SurveyChatbotSession.objects.get(user=self.user)
        self.assertEqual(str(new_session.id), str(reset_response.data["session_id"]))
        self.assertEqual(new_session.status, SurveyStatusChoices.OPEN)
        self.assertIsNone(new_session.target_question_count)

        messages = list(SurveyChatbotMessage.objects.filter(session=new_session))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, SurveyRoleChoices.AI)
        self.assertEqual(messages[0].sequence, 1)


class SurveyChatbotSessionServiceTest(TestCase):
    def test_initialize_session_clears_existing_result(self) -> None:
        user = create_user()
        session = SurveyChatbotSession.objects.create(
            user=user,
            status=SurveyStatusChoices.IN_PROGRESS,
            target_question_count=3,
        )
        SurveyChatbotMessage.objects.create(
            session=session,
            message="이전 질문",
            role=SurveyRoleChoices.AI,
            sequence=1,
        )
        SurveyResults.objects.create(
            chatbot_session=session,
            user=user,
            survey_answer="이전 요약",
        )
        service = SurveyChatbotSessionService()

        with patch.object(
            service,
            "generate_first_question",
            return_value=TEST_FIRST_QUESTION,
        ):
            service.initialize_session(session)

        session.refresh_from_db()
        self.assertEqual(session.status, SurveyStatusChoices.OPEN)
        self.assertIsNone(session.target_question_count)
        self.assertFalse(SurveyResults.objects.filter(user=user).exists())
        self.assertEqual(session.messages.count(), 1)

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY=None)
    def test_generate_first_question_raises_without_api_key(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch("apps.survey.services.survey_chatbot_session.logging"),
            self.assertRaises(SurveyQuestionGenerationUnavailable),
        ):
            service.generate_first_question()

    def test_extract_text_from_gemini_response(self) -> None:
        service = SurveyChatbotSessionService()
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "어떤 게임 경험이 가장 오래 기억에 남았는지 알려주세요."
                            }
                        ]
                    }
                }
            ]
        }

        text = service.extract_text_from_gemini_response(data)

        self.assertEqual(
            text,
            "어떤 게임 경험이 가장 오래 기억에 남았는지 알려주세요.",
        )

    def test_extract_text_from_gemini_response_joins_multiple_parts(self) -> None:
        service = SurveyChatbotSessionService()
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "최근 가장 오래 몰입했던 게임에서 "},
                            {"text": "어떤 요소가 좋았는지 알려주세요."},
                        ]
                    }
                }
            ]
        }

        text = service.extract_text_from_gemini_response(data)

        self.assertEqual(
            text,
            "최근 가장 오래 몰입했던 게임에서 어떤 요소가 좋았는지 알려주세요.",
        )

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-api-key")
    def test_generate_question_with_llm_success(self) -> None:
        service = SurveyChatbotSessionService()
        response = Mock()
        response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "몰입했던 게임 경험을 알려주세요."}]}}
            ]
        }

        with patch(
            "apps.survey.services.survey_chatbot_session.requests.post",
            return_value=response,
        ) as mocked_post:
            question = service.generate_question_with_llm("질문 생성 요청")

        self.assertEqual(question, "몰입했던 게임 경험을 알려주세요.")
        response.raise_for_status.assert_called_once()
        mocked_post.assert_called_once()
        request_payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(
            request_payload["contents"][0]["parts"][0]["text"],
            "질문 생성 요청",
        )
        self.assertNotIn("systemInstruction", request_payload)
        self.assertEqual(request_payload["generationConfig"]["maxOutputTokens"], 1024)
        self.assertEqual(
            request_payload["generationConfig"]["responseMimeType"],
            "text/plain",
        )

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-api-key")
    def test_generate_question_with_llm_logs_empty_response(self) -> None:
        service = SurveyChatbotSessionService()
        response = Mock()
        response.json.return_value = {"candidates": [{"content": {"parts": []}}]}

        with (
            patch(
                "apps.survey.services.survey_chatbot_session.requests.post",
                return_value=response,
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_question_with_llm("프롬프트")

        self.assertIsNone(question)
        logging.getLogger.return_value.warning.assert_called_once()

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-api-key")
    def test_generate_question_with_llm_returns_none_on_request_error(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch(
                "apps.survey.services.survey_chatbot_session.requests.post",
                side_effect=requests.RequestException,
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_question_with_llm("프롬프트")

        self.assertIsNone(question)
        logging.getLogger.return_value.exception.assert_called_once()

    def test_extract_text_from_gemini_response_returns_none_for_invalid_data(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        self.assertIsNone(service.extract_text_from_gemini_response({}))

    def test_extract_text_from_gemini_response_returns_none_for_blank_text(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()
        data = {"candidates": [{"content": {"parts": [{"text": "   "}]}}]}

        self.assertIsNone(service.extract_text_from_gemini_response(data))

    def test_generate_first_question_rejects_partial_llm_response(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value="최근 가장 인상",
            ) as generate_question,
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            with self.assertRaises(SurveyQuestionGenerationUnavailable):
                service.generate_first_question()

        generate_question.assert_called_once_with(service.load_first_question_prompt())
        logging.getLogger.return_value.warning.assert_called_once()

    def test_generate_first_question_uses_valid_llm_response(self) -> None:
        service = SurveyChatbotSessionService()

        with patch.object(
            service,
            "generate_question_with_llm",
            return_value=TEST_FIRST_QUESTION,
        ):
            question = service.generate_first_question()

        self.assertEqual(question, TEST_FIRST_QUESTION)

    def test_is_complete_first_question(self) -> None:
        service = SurveyChatbotSessionService()

        self.assertTrue(service.is_complete_first_question(TEST_FIRST_QUESTION))
        self.assertFalse(service.is_complete_first_question("최근 가장 인상"))
        self.assertFalse(service.is_complete_first_question(None))

    def test_generate_first_question_raises_without_llm_response(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(service, "generate_question_with_llm", return_value=None),
            patch("apps.survey.services.survey_chatbot_session.logging"),
        ):
            with self.assertRaises(SurveyQuestionGenerationUnavailable):
                service.generate_first_question()
