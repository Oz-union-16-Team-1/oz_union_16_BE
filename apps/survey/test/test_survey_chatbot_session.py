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
from apps.survey.prompts.survey_chatbot_prompt import SURVEY_CHATBOT_PROMPT
from apps.survey.services.survey_chatbot_session import (
    SURVEY_COMPLETION_MESSAGE,
    SurveyChatbotSessionService,
)
from apps.users.models import User

TEST_FIRST_QUESTION = "최근 가장 재미있게 즐긴 게임은 어떤 종류였고, 어떤 점 때문에 계속 플레이하게 되었는지 말씀해 주세요."


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

        second_response = self.client.post(self.url, {}, format="json")

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            second_response.data["session_id"], first_response.data["session_id"]
        )
        self.assertEqual(
            second_response.data["ai_question"], first_response.data["ai_question"]
        )
        self.assertEqual(SurveyChatbotSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SurveyChatbotMessage.objects.count(), 1)

    def test_create_session_without_reset_keeps_closed_session_data(self) -> None:
        self.authenticate()
        session = SurveyChatbotSession.objects.create(
            user=self.user,
            status=SurveyStatusChoices.CLOSED,
            target_question_count=3,
        )
        SurveyChatbotMessage.objects.create(
            session=session,
            role=SurveyRoleChoices.AI,
            sequence=1,
            message="마지막 질문입니다.",
        )
        SurveyChatbotMessage.objects.create(
            session=session,
            role=SurveyRoleChoices.USER,
            sequence=2,
            message="마지막 답변입니다.",
        )
        SurveyResults.objects.create(
            chatbot_session=session,
            user=self.user,
            survey_answer="완료된 설문 요약",
        )

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["session_id"], str(session.id))
        self.assertEqual(response.data["status"], SurveyStatusChoices.CLOSED)
        self.assertEqual(response.data["ai_question"], SURVEY_COMPLETION_MESSAGE)
        self.assertTrue(response.data["recommendation_ready"])

        session.refresh_from_db()
        self.assertEqual(session.status, SurveyStatusChoices.CLOSED)
        self.assertEqual(session.messages.count(), 2)
        self.assertTrue(SurveyResults.objects.filter(chatbot_session=session).exists())

    def test_create_session_closed_session_without_ai_message_does_not_generate_question(
        self,
    ) -> None:
        self.authenticate()
        session = SurveyChatbotSession.objects.create(
            user=self.user,
            status=SurveyStatusChoices.CLOSED,
            target_question_count=1,
        )
        SurveyChatbotMessage.objects.create(
            session=session,
            role=SurveyRoleChoices.USER,
            sequence=1,
            message="완료된 답변입니다.",
        )
        SurveyResults.objects.create(
            chatbot_session=session,
            user=self.user,
            survey_answer="완료된 설문 요약",
        )

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["session_id"], str(session.id))
        self.assertEqual(response.data["status"], SurveyStatusChoices.CLOSED)
        self.assertEqual(response.data["ai_question"], SURVEY_COMPLETION_MESSAGE)
        self.assertTrue(response.data["recommendation_ready"])
        self.assertEqual(
            SurveyChatbotMessage.objects.filter(session=session).count(), 1
        )


class SurveyChatbotSessionResetAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("survey-chatbot-session-reset")

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
        response = self.client.post(self.url, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reset_session_creates_fresh_session(self) -> None:
        self.authenticate()
        old_session = SurveyChatbotSession.objects.create(
            user=self.user,
            status=SurveyStatusChoices.IN_PROGRESS,
            target_question_count=3,
        )
        SurveyChatbotMessage.objects.create(
            session=old_session,
            role=SurveyRoleChoices.AI,
            sequence=1,
            message="이전 질문",
        )
        SurveyChatbotMessage.objects.create(
            session=old_session,
            role=SurveyRoleChoices.USER,
            sequence=2,
            message="이전 답변",
        )
        SurveyResults.objects.create(
            chatbot_session=old_session,
            user=self.user,
            survey_answer="이전 요약",
        )

        response = self.client.post(self.url, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], SurveyStatusChoices.OPEN)
        self.assertEqual(
            response.data["progress"],
            {
                "current_step": 0,
                "total_steps": None,
                "completion_rate": None,
            },
        )
        self.assertFalse(
            SurveyChatbotSession.objects.filter(id=old_session.id).exists()
        )

        new_session = SurveyChatbotSession.objects.get(user=self.user)
        self.assertEqual(str(new_session.id), str(response.data["session_id"]))
        self.assertEqual(new_session.messages.count(), 1)
        self.assertEqual(
            new_session.messages.first().message,
            f"{self.user.nickname}님은 {TEST_FIRST_QUESTION}",
        )

    def test_reset_session_without_existing_session_creates_new_one(self) -> None:
        self.authenticate()

        response = self.client.post(self.url, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], SurveyStatusChoices.OPEN)
        self.assertEqual(SurveyChatbotSession.objects.filter(user=self.user).count(), 1)


class SurveyChatbotSessionServiceTest(TestCase):
    def test_default_prompt_constant_exists(self) -> None:
        self.assertIn("게임 추천을 위한 게임 취향 설문 챗봇", SURVEY_CHATBOT_PROMPT)
        self.assertIn(
            "{nickname}님이 자신의 실제 플레이 경험을 자연스럽게 떠올리도록 유도",
            SURVEY_CHATBOT_PROMPT,
        )

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
    def test_generate_first_question_uses_fallback_without_api_key(self) -> None:
        service = SurveyChatbotSessionService()

        with patch("apps.survey.services.survey_chatbot_session.logging"):
            question = service.generate_first_question()

        self.assertEqual(
            question, service.SAFE_FALLBACK_QUESTIONS[0].format(nickname="사용자")
        )

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
        self.assertEqual(request_payload["generationConfig"]["temperature"], 0.4)
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
            question = service.generate_first_question()

        called_prompt = generate_question.call_args.args[0]
        self.assertEqual(service.build_first_question_prompt(), called_prompt)
        self.assertEqual(generate_question.call_args.kwargs["temperature"], 0.85)
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 1)
        self.assertEqual(
            question, service.SAFE_FALLBACK_QUESTIONS[0].format(nickname="사용자")
        )

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
        self.assertTrue(
            service.is_complete_first_question(
                "최근 가장 오래 플레이했던 게임에서는 어떤 순간 때문에 계속 접속하게 되었는지 말씀해 주세요."
            )
        )
        self.assertTrue(
            service.is_complete_first_question(
                "최근 재미있게 즐긴 게임에서 가장 만족감이 컸던 플레이 경험이 어떤 상황이었는지 말씀해 주세요."
            )
        )
        self.assertFalse(
            service.is_complete_first_question(
                "적의 진입 경로를 예측해 막아내는 재미와 직접 먼저 제압하는 재미 중 어느 쪽이 더 큰가요"
            )
        )
        self.assertFalse(service.is_complete_first_question("최근 가장 인상"))
        self.assertFalse(service.is_complete_first_question(None))

    def test_is_valid_survey_question_rejects_yes_no_question(self) -> None:
        service = SurveyChatbotSessionService()

        self.assertFalse(
            service.is_valid_survey_question(
                "어떤 전투 상황에서 적을 제압하는 순간이 가장 즐거우신가요?"
            )
        )
        self.assertTrue(service.is_valid_survey_question(TEST_FIRST_QUESTION))
        self.assertTrue(
            service.is_valid_survey_question(
                "화려하고 빠른 전투를 반복해서 돌파하는 플레이와 묵직하고 전략적인 전투를 준비해 해결하는 플레이 중 어느 쪽이 더 끌리나요?",
                mode="NEXT",
            )
        )
        self.assertTrue(
            service.is_valid_survey_question(
                "적의 진입 경로를 예측해 막아내는 재미와 직접 먼저 제압하는 재미 중 어느 쪽이 더 큰가요",
                mode="NEXT",
            )
        )
        self.assertFalse(service.is_valid_survey_question("전투가 즐거우신가요"))

    def test_is_valid_survey_question_allows_broad_question_to_avoid_blocking(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        self.assertTrue(
            service.is_valid_survey_question(
                "게임에서 어떤 경험을 중요하게 생각하시는지 자세히 말씀해 주세요.",
                mode="NEXT",
            )
        )
        self.assertTrue(
            service.is_valid_survey_question(
                "어떤 게임 스타일을 좋아하는지 자세히 말씀해 주세요.",
                mode="NEXT",
            )
        )

    def test_is_valid_survey_question_allows_repeated_question_to_avoid_blocking(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        self.assertTrue(
            service.is_valid_survey_question(
                "평소 좋아하는 게임 장르나 플레이 스타일은 무엇이며, 그런 게임을 좋아하게 되는 이유도 함께 알려주세요.",
                previous_questions=[
                    "평소 선호하는 게임 장르와 플레이 방식은 무엇이며, 그런 게임을 좋아하는 이유를 알려주세요."
                ],
            )
        )

    def test_generate_first_question_uses_fallback_without_llm_response(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(service, "generate_question_with_llm", return_value=None),
            patch("apps.survey.services.survey_chatbot_session.logging"),
        ):
            question = service.generate_first_question()

        self.assertEqual(
            question, service.SAFE_FALLBACK_QUESTIONS[0].format(nickname="사용자")
        )

    def test_build_first_question_prompt_uses_prompt_file_without_extra_text(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        prompt = service.build_first_question_prompt()

        self.assertEqual(
            service.load_first_question_prompt().format(nickname="사용자"),
            prompt,
        )

    def test_generate_valid_question_repairs_yes_no_question(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value="팀원들과 즉흥적으로 새로운 전술을 짜내 승리했을 때 더 큰 쾌감을 느끼시나요?",
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
            )

        self.assertEqual(
            question,
            "팀원들과 즉흥적으로 새로운 전술을 짜내 승리했을 때 더 큰 쾌감을 느끼는 이유나 기억나는 장면을 말씀해 주세요.",
        )
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 0)

    def test_generate_valid_question_returns_fallback_after_single_failure(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value="최근 가장 인상",
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
            )

        self.assertEqual(
            question, service.SAFE_FALLBACK_QUESTIONS[0].format(nickname="사용자")
        )
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 1)
