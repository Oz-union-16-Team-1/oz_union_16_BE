import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chatbot.models.models import ChatbotMessage, ChatbotSession
from apps.chatbot.services.chatbot_llm_services import GeminiUnavailable
from apps.chatbot.services.chatbot_messages_services import save_question_to_cache
from apps.chatbot.services.chatbot_streaming_services import LLM_FAILURE_MESSAGE


def _collect_stream_chunks(content: str) -> str:
    chunks: list[str] = []
    current_event: str | None = None

    for line in content.splitlines():
        if line.startswith("event: "):
            current_event = line.replace("event: ", "", 1).strip()
        elif line.startswith("data: "):
            payload = json.loads(line.replace("data: ", "", 1))
            if current_event == "chunk":
                chunks.append(payload["content"])

    return "".join(chunks)


def _collect_events(content: str) -> list[str]:
    events: list[str] = []
    for line in content.splitlines():
        if line.startswith("event: "):
            events.append(line.replace("event: ", "", 1).strip())
    return events


class ChatbotMessagesAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.messages_url = "/api/v1/chatbot/messages"

    def test_message_create_success(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={"message": "게임 추천은 어떻게 받아요?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIn("session_id", response_data)
        self.assertIn("expires_at", response_data)
        self.assertNotIn("expires_in_seconds", response_data)
        self.assertNotIn("session_ttl_seconds", response_data)

    def test_message_create_fail_when_message_too_short(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={"message": "가"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error_detail", response.json())

    def test_message_create_fail_with_invalid_session_id(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={
                "message": "게임 추천은 어떻게 받아요?",
                "session_id": "bf95b479-04c3-423d-878e-22a8dbce9999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error_detail"],
            "만료되었거나 유효하지 않은 session_id 입니다.",
        )

    def test_message_create_fail_with_malformed_session_id_returns_404(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={
                "message": "게임 추천은 어떻게 받아요?",
                "session_id": "not-a-session-id",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error_detail"],
            "만료되었거나 유효하지 않은 session_id 입니다.",
        )

    def test_message_create_overwrites_pending_question(self) -> None:
        first = self.client.post(
            self.messages_url,
            data={"message": "첫 번째 질문입니다."},
            format="json",
        )
        session_id = first.json()["session_id"]

        second = self.client.post(
            self.messages_url,
            data={"message": "덮어쓴 질문입니다.", "session_id": session_id},
            format="json",
        )

        self.assertEqual(second.status_code, 200)
        session = ChatbotSession.objects.get(pk=session_id)
        self.assertEqual(session.pending_question, "덮어쓴 질문입니다.")


class ChatbotStreamAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.messages_url = "/api/v1/chatbot/messages"
        self.stream_url = "/api/v1/chatbot/stream"

    def _create_session_with_question(self, question: str) -> str:
        message_response = self.client.post(
            self.messages_url,
            data={"message": question},
            format="json",
        )
        self.assertEqual(message_response.status_code, 200)
        return message_response.json()["session_id"]

    @patch("apps.chatbot.services.chatbot_streaming_services.stream_answer")
    def test_stream_success_streams_llm_chunks(self, mock_stream_answer) -> None:
        mock_stream_answer.return_value = iter(["안녕하세요. ", "도움을 ", "드릴게요."])

        session_id = self._create_session_with_question("별점은 어디에 쓰이나요?")

        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )

        self.assertEqual(stream_response.status_code, 200)
        self.assertEqual(stream_response["Content-Type"], "text/event-stream")

        content = b"".join(stream_response.streaming_content).decode("utf-8")

        events = _collect_events(content)
        self.assertEqual(events[0], "start")
        self.assertEqual(events[-1], "complete")
        self.assertIn("chunk", events)
        self.assertNotIn("suggestions", events)

        self.assertEqual(
            _collect_stream_chunks(content),
            "안녕하세요. 도움을 드릴게요.",
        )

        contents = mock_stream_answer.call_args.args[0]
        self.assertEqual(
            contents,
            [{"role": "user", "parts": [{"text": "별점은 어디에 쓰이나요?"}]}],
        )

        session = ChatbotSession.objects.get(pk=session_id)
        saved = list(session.messages.order_by("created_at"))
        self.assertEqual([m.role for m in saved], ["user", "assistant"])
        self.assertEqual(saved[0].content, "별점은 어디에 쓰이나요?")
        self.assertEqual(saved[1].content, "안녕하세요. 도움을 드릴게요.")

    @patch("apps.chatbot.services.chatbot_streaming_services.stream_answer")
    def test_stream_falls_back_when_llm_unavailable(self, mock_stream_answer) -> None:
        def _raising_iter():
            raise GeminiUnavailable("upstream down")
            yield  # pragma: no cover

        mock_stream_answer.return_value = _raising_iter()

        session_id = self._create_session_with_question("회원가입은 어떻게 하나요?")

        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )

        content = b"".join(stream_response.streaming_content).decode("utf-8")
        self.assertEqual(_collect_stream_chunks(content), LLM_FAILURE_MESSAGE)

    @patch("apps.chatbot.services.chatbot_streaming_services.stream_answer")
    def test_stream_consumes_pending_question(self, mock_stream_answer) -> None:
        mock_stream_answer.return_value = iter(["응답."])
        session_id = self._create_session_with_question("질문입니다.")

        first = self.client.get(self.stream_url, data={"session_id": session_id})
        self.assertEqual(first.status_code, 200)
        b"".join(first.streaming_content)

        second = self.client.get(self.stream_url, data={"session_id": session_id})
        self.assertEqual(second.status_code, 404)
        self.assertEqual(
            second.json()["error_detail"],
            "스트리밍 대상 질문이 없습니다.",
        )

    def test_stream_fail_when_session_id_missing(self) -> None:
        response = self.client.get(self.stream_url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_detail"],
            "session_id는 필수 입력값입니다.",
        )

    def test_stream_accepts_event_stream_header(self) -> None:
        response = self.client.get(
            self.stream_url,
            HTTP_ACCEPT="text/event-stream",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_detail"],
            "session_id는 필수 입력값입니다.",
        )

    def test_stream_fail_when_session_not_found(self) -> None:
        response = self.client.get(
            self.stream_url,
            data={"session_id": "bf95b479-04c3-423d-878e-22a8dbce9999"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error_detail"],
            "스트리밍 대상 세션을 찾을 수 없습니다.",
        )

    def test_stream_fail_with_malformed_session_id_returns_400(self) -> None:
        response = self.client.get(
            self.stream_url,
            data={"session_id": "not-a-session-id"},
            HTTP_ACCEPT="text/event-stream",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_detail"],
            "잘못된 session_id 입니다.",
        )

    def test_stream_fail_when_question_not_in_cache(self) -> None:
        session = ChatbotSession.objects.create(
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = self.client.get(
            self.stream_url,
            data={"session_id": str(session.pk)},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error_detail"],
            "스트리밍 대상 질문이 없습니다.",
        )

    def test_stream_fail_when_session_expired(self) -> None:
        expired_session = ChatbotSession.objects.create(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        save_question_to_cache(expired_session.pk, "게임 추천은 어떻게 받아요?")

        response = self.client.get(
            self.stream_url,
            data={"session_id": str(expired_session.pk)},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error_detail"],
            "스트리밍 대상 세션을 찾을 수 없습니다.",
        )


class ChatbotSessionStatusAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_session_status_success(self) -> None:
        session = ChatbotSession.objects.create(
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = self.client.get(f"/api/v1/chatbot/sessions/{session.pk}")

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(response_data["session_id"], str(session.pk))
        self.assertFalse(response_data["is_expired"])
        self.assertIn("expires_at", response_data)
        self.assertGreater(response_data["expires_in_seconds"], 0)
        self.assertEqual(response_data["session_ttl_seconds"], 1800)

    def test_session_status_expired(self) -> None:
        session = ChatbotSession.objects.create(
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get(f"/api/v1/chatbot/sessions/{session.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_expired"])
        self.assertEqual(response.json()["expires_in_seconds"], 0)
