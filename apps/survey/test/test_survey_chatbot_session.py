import uuid
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.igdb import IGDB
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
            "첫 질문부터 사용자의 추천 취향 축을 바로 확인",
            SURVEY_CHATBOT_PROMPT,
        )
        self.assertIn(
            "최근 플레이 경험, 기억나는 장면, 만족했던 순간을 묻지 않습니다.",
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
    def test_generate_question_with_llm_uses_system_instruction(self) -> None:
        service = SurveyChatbotSessionService()
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "질문을 말씀해 주세요."}]}}]
        }

        with patch(
            "apps.survey.services.survey_chatbot_session.requests.post",
            return_value=response,
        ) as mocked_post:
            service.generate_question_with_llm(
                "유저 프롬프트",
                system_prompt="시스템 프롬프트",
            )

        request_payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(
            request_payload["systemInstruction"]["parts"][0]["text"],
            "시스템 프롬프트",
        )
        self.assertEqual(
            request_payload["contents"][0]["parts"][0]["text"],
            "유저 프롬프트",
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

        called_prompt = generate_question.call_args_list[0].args[0]
        self.assertEqual(service.build_first_question_prompt(), called_prompt)
        self.assertEqual(
            generate_question.call_args_list[0].kwargs["temperature"], 0.85
        )
        self.assertEqual(
            logging.getLogger.return_value.warning.call_count,
            service.QUESTION_GENERATION_MAX_ATTEMPTS,
        )
        self.assertEqual(
            question, service.SAFE_FALLBACK_QUESTIONS[0].format(nickname="사용자")
        )

    def test_generate_first_question_uses_valid_llm_response(self) -> None:
        service = SurveyChatbotSessionService()

        with patch.object(
            service,
            "generate_question_with_llm",
            side_effect=[None, "최근 가장 인상", TEST_FIRST_QUESTION],
        ) as generate_question:
            question = service.generate_first_question()

        self.assertEqual(question, TEST_FIRST_QUESTION)
        self.assertEqual(generate_question.call_count, 3)

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
        self.assertTrue(
            service.is_complete_first_question(
                "혼자 깊게 몰입하는 플레이와 다른 사람과 협력하거나 경쟁하는 플레이 중 어느 쪽이 더 잘 맞나요?"
            )
        )
        self.assertTrue(
            service.is_complete_first_question(
                "적의 진입 경로를 예측해 막아내는 재미와 직접 먼저 제압하는 재미 중 어느 쪽이 더 큰가요"
            )
        )
        self.assertFalse(service.is_complete_first_question("최근 가장 인상"))
        self.assertFalse(service.is_complete_first_question(None))

    def test_is_valid_survey_question_allows_question_like_sentence(self) -> None:
        service = SurveyChatbotSessionService()

        self.assertTrue(
            service.is_valid_survey_question(
                "어떤 전투 상황에서 적을 제압하는 순간이 가장 즐거우신가요?"
            )
        )
        self.assertTrue(service.is_valid_survey_question(TEST_FIRST_QUESTION))
        self.assertTrue(
            service.is_valid_survey_question(
                "혼자 깊게 몰입하는 플레이와 다른 사람과 협력하거나 경쟁하는 플레이 중 어느 쪽이 더 잘 맞나요?"
            )
        )
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
        self.assertTrue(
            service.is_valid_survey_question(
                "빠른 전투를 진행하는 플레이가 즐거우신가요?"
            )
        )
        self.assertFalse(service.is_valid_survey_question("전투"))

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

    def test_generate_valid_question_keeps_natural_yes_no_question(self) -> None:
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
            "팀원들과 즉흥적으로 새로운 전술을 짜내 승리했을 때 더 큰 쾌감을 느끼시나요?",
        )
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 0)

    def test_generate_valid_question_polishes_repeated_side_expression(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value=(
                    "qwer님은 협동 플레이와 경쟁 플레이 중 어느 쪽에 "
                    "더 흥미를 느끼는 쪽인지 편하게 말씀해 주세요."
                ),
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            "qwer님은 협동 플레이와 경쟁 플레이 중 어느 쪽에 더 흥미를 느끼는지 편하게 말씀해 주세요.",
        )
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 0)

    def test_generate_valid_question_repairs_incomplete_question_ending(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value=(
                    "qwer님은 혼자 깊이 몰입해 전략을 세우는 재미와 다른 사람과 "
                    "빠르게 협력하거나 경쟁하며 순발력을 발휘하는 재미 중 어떤 것을 더 선"
                ),
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            (
                "qwer님은 혼자 깊이 몰입해 전략을 세우는 재미와 다른 사람과 "
                "빠르게 협력하거나 경쟁하며 순발력을 발휘하는 재미 중 어느 쪽이 더 잘 맞는지 편하게 말씀해 주세요."
            ),
        )
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 0)

    def test_generate_valid_question_does_not_duplicate_comparison_tail(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value=(
                    "qwer님은 목표를 극복할 때, 차분히 계획을 세워 해결하는 재미와 "
                    "빠르게 반응하며 돌파하는 재미 중 어느 쪽이 더 좋으신가"
                ),
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            (
                "qwer님은 목표를 극복할 때, 차분히 계획을 세워 해결하는 재미와 "
                "빠르게 반응하며 돌파하는 재미 중 어느 쪽이 더 좋으신가요?"
            ),
        )
        self.assertNotIn("중 어느 쪽이 더 좋으신가 중", question or "")
        self.assertEqual(logging.getLogger.return_value.warning.call_count, 0)

    def test_generate_valid_question_falls_back_for_unrepairable_cut_sentence(
        self,
    ) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value=(
                    "qwer님은 탐험하며 퍼즐을 풀거나 환경과 상호작용하는 것 외에, "
                    "강력한 적이나 위협적인 존재를 극복하는 재미도 중요하게 생각하시"
                ),
            ),
            patch("apps.survey.services.survey_chatbot_session.logging") as logging,
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                mode="NEXT",
                latest_user_message="탐험하며 퍼즐을 푸는 게임이 좋아요.",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            (
                "qwer님은 숨겨진 장소를 자유롭게 찾는 탐험과 단서를 따라 "
                "세계를 이해하는 진행 중 어느 쪽이 더 끌리는지 말씀해 주세요."
            ),
        )
        if question is None:
            self.fail("question should not be None")
        assert question is not None
        self.assertLessEqual(len(question), service.QUESTION_MAX_LENGTH)
        self.assertEqual(
            logging.getLogger.return_value.warning.call_count,
            service.QUESTION_GENERATION_MAX_ATTEMPTS,
        )

    def test_generate_valid_question_returns_fallback_after_three_failures(
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
        self.assertEqual(
            logging.getLogger.return_value.warning.call_count,
            service.QUESTION_GENERATION_MAX_ATTEMPTS,
        )

    def test_generate_valid_question_uses_contextual_next_fallback(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value="최근 가장 인상",
            ),
            patch("apps.survey.services.survey_chatbot_session.logging"),
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                mode="NEXT",
                latest_user_message="팀원들과 전략을 짜서 사이트를 뚫는 재미가 좋아요.",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            "qwer님은 슈팅 게임에서 직접 진입하는 역할과 정보를 보고 마무리하는 역할 중 어느 쪽이 더 편한지 말씀해 주세요.",
        )

    def test_generate_valid_question_uses_short_retry_prompts(self) -> None:
        service = SurveyChatbotSessionService()

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                side_effect=[
                    None,
                    None,
                    "qwer님은 혼자/협동/경쟁 중 어떤 방식이 게임을 고를 때 더 중요한지 말씀해 주세요.",
                ],
            ) as generate_question,
            patch("apps.survey.services.survey_chatbot_session.logging"),
        ):
            question = service.generate_valid_question(
                prompt="원본 프롬프트",
                system_prompt="원본 시스템 프롬프트",
                temperature=0.4,
                log_message="invalid: %s",
                mode="NEXT",
                latest_user_message="팀원이랑 하는 게 좋아요.",
                nickname="qwer",
            )

        self.assertEqual(
            question,
            "qwer님은 혼자/협동/경쟁 중 어떤 방식이 게임을 고를 때 더 중요한지 말씀해 주세요.",
        )
        first_call, second_call, third_call = generate_question.call_args_list
        self.assertEqual(first_call.args[0], "원본 프롬프트")
        self.assertIn("직전 사용자 답변: 팀원이랑 하는 게 좋아요.", second_call.args[0])
        self.assertIn("아래 질문 문장을 그대로 출력하세요.", third_call.args[0])
        self.assertEqual(first_call.kwargs["system_prompt"], "원본 시스템 프롬프트")
        self.assertNotEqual(second_call.kwargs["system_prompt"], "원본 시스템 프롬프트")
        self.assertEqual(third_call.kwargs["temperature"], 0.3)

    def test_generate_valid_question_skips_repeated_fallback_question(self) -> None:
        service = SurveyChatbotSessionService()
        repeated_question = (
            "qwer님은 혼자 진행하는 방식과 다른 사람과 함께하는 방식 중 "
            "어느 쪽이 더 편한지 말씀해 주세요."
        )

        with (
            patch.object(
                service,
                "generate_question_with_llm",
                return_value="최근 가장 인상",
            ),
            patch("apps.survey.services.survey_chatbot_session.logging"),
        ):
            question = service.generate_valid_question(
                prompt="prompt",
                temperature=0.4,
                log_message="invalid: %s",
                mode="NEXT",
                latest_user_message="재미가 좋아요.",
                previous_questions=[repeated_question],
                nickname="qwer",
            )

        self.assertNotEqual(question, repeated_question)
        self.assertEqual(
            question,
            (
                "qwer님은 방금 말한 취향이 빠르게 판단하는 쪽과 차근차근 "
                "준비하는 쪽 중 어디에 더 가까운지 편하게 말씀해 주세요."
            ),
        )

    def test_contextual_next_fallback_does_not_return_fixed_fun_question(self) -> None:
        service = SurveyChatbotSessionService()

        fallback_pool = service.build_contextual_fallback_pool(
            mode="NEXT",
            nickname="qwer",
            latest_user_message="재미가 좋아요.",
        )

        self.assertNotIn(
            "전투의 긴장감, 성장의 성취감, 탐험의 발견감", fallback_pool[0]
        )
        self.assertNotIn("방금 말한 경험", fallback_pool[0])
        self.assertNotIn("결정적이었던 행동", fallback_pool[0])
        self.assertIn("혼자 진행하는 방식", fallback_pool[0])

    def test_contextual_next_fallback_covers_all_igdb_genres(self) -> None:
        service = SurveyChatbotSessionService()
        covered_genres = {
            genre_name for genre_name, _, _ in service.CONTEXTUAL_NEXT_FALLBACK_RULES
        }

        self.assertEqual(set(IGDB.GENRE_NAME_MAP.values()), covered_genres)

    def test_contextual_next_fallback_uses_genre_specific_templates(self) -> None:
        service = SurveyChatbotSessionService()

        cases = (
            (
                "보스를 잡고 장비를 맞춰서 성장하는 RPG가 좋아요.",
                "장비나 빌드를 준비해 강해지는 재미",
            ),
            (
                "상대 콤보를 막고 카운터로 이기는 격투가 좋아요.",
                "상대 패턴을 읽고 반격하는 플레이",
            ),
            (
                "숨겨진 지역을 발견하는 어드벤처 탐험이 좋아요.",
                "숨겨진 장소를 자유롭게 찾는 탐험",
            ),
        )
        for message, expected_text in cases:
            with self.subTest(message=message):
                fallback_pool = service.build_contextual_fallback_pool(
                    mode="NEXT",
                    nickname="qwer",
                    latest_user_message=message,
                )

                self.assertIn(expected_text, fallback_pool[0])
                self.assertNotIn("장면", fallback_pool[0])
                self.assertNotIn("순간", fallback_pool[0])
