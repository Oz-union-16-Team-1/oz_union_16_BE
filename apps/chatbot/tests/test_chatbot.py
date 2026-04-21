import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chatbot.models.models import ChatbotSession
from apps.chatbot.services.chatbot_services import save_question_to_cache


class ChatbotAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.messages_url = "/api/v1/chatbot/messages"
        self.stream_url = "/api/v1/chatbot/stream"

    def test_message_create_success(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={"message": "환불은 어떻게 해요?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("session_id", response.json())

    def test_message_create_fail_when_message_too_short(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={"message": "가"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_message_create_fail_with_invalid_session_id(self) -> None:
        response = self.client.post(
            self.messages_url,
            data={
                "message": "환불은 어떻게 해요?",
                "session_id": "bf95b479-04c3-423d-878e-22a8dbce9999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "만료되었거나 유효하지 않은 session_id 입니다.",
        )

    def test_stream_success_after_message_saved(self) -> None:
        message_response = self.client.post(
            self.messages_url,
            data={"message": "환불은 어떻게 해요?"},
            format="json",
        )
        self.assertEqual(message_response.status_code, 200)

        session_id = message_response.json()["session_id"]

        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )

        self.assertEqual(stream_response.status_code, 200)
        self.assertEqual(stream_response["Content-Type"], "text/event-stream")

        content = b"".join(stream_response.streaming_content).decode("utf-8")

        self.assertIn("event: start", content)
        self.assertIn("event: chunk", content)
        self.assertIn("event: complete", content)

        chunks: list[str] = []
        current_event: str | None = None

        for line in content.splitlines():
            if line.startswith("event: "):
                current_event = line.replace("event: ", "", 1).strip()
            elif line.startswith("data: "):
                payload = json.loads(line.replace("data: ", "", 1))
                if current_event == "chunk":
                    chunks.append(payload["content"])

        final_message = "".join(chunks)

        self.assertEqual(
            final_message,
            "환불 관련 문의는 결제 내역 또는 고객센터를 통해 확인하실 수 있습니다.",
        )

    def test_stream_fail_when_session_id_missing(self) -> None:
        response = self.client.get(self.stream_url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "잘못된 session_id 입니다.")

    def test_stream_fail_when_session_not_found(self) -> None:
        response = self.client.get(
            self.stream_url,
            data={"session_id": "bf95b479-04c3-423d-878e-22a8dbce9999"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "스트리밍 대상 세션을 찾을 수 없습니다.")

    def test_stream_fail_when_question_not_in_cache(self) -> None:
        session = ChatbotSession.objects.create(
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = self.client.get(
            self.stream_url,
            data={"session_id": str(session.pk)},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "스트리밍 대상 질문이 없습니다.")

    def test_stream_fail_when_session_expired(self) -> None:
        expired_session = ChatbotSession.objects.create(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        save_question_to_cache(expired_session.pk, "환불은 어떻게 해요?")

        response = self.client.get(
            self.stream_url,
            data={"session_id": str(expired_session.pk)},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "스트리밍 대상 세션을 찾을 수 없습니다.")