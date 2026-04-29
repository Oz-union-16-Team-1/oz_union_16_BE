import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chatbot.models.models import ChatbotSession
from apps.chatbot.services.chatbot_services import build_answer, save_question_to_cache


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


class ChatbotAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.messages_url = "/api/v1/chatbot/messages"
        self.stream_url = "/api/v1/chatbot/stream"

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
        self.assertIn("expires_in_seconds", response_data)
        self.assertEqual(response_data["session_ttl_seconds"], 1800)
        self.assertGreater(response_data["expires_in_seconds"], 0)

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

    def test_stream_success_after_message_saved(self) -> None:
        message_response = self.client.post(
            self.messages_url,
            data={"message": "별점은 어디에 쓰이나요?"},
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
        self.assertIn("expires_at", content)
        self.assertIn("expires_in_seconds", content)

        self.assertEqual(
            _collect_stream_chunks(content),
            "별점은 게임에 대한 사용자 평가로 활용되며, 인기 TOP100 게임을 보여주는 기준에 반영됩니다.",
        )

    def test_message_uses_site_knowledge_base(self) -> None:
        message_response = self.client.post(
            self.messages_url,
            data={"message": "게임 추천은 어떻게 되나요?"},
            format="json",
        )
        self.assertEqual(message_response.status_code, 200)

        session_id = message_response.json()["session_id"]
        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )

        content = b"".join(stream_response.streaming_content).decode("utf-8")

        self.assertEqual(
            _collect_stream_chunks(content),
            "게임 추천은 설문조사 답변과 사용자의 장르, 스타일 취향을 바탕으로 어울리는 게임을 안내하는 기능입니다.",
        )

    def test_message_blocks_out_of_scope_question(self) -> None:
        message_response = self.client.post(
            self.messages_url,
            data={"message": "오늘 날씨 알려줘"},
            format="json",
        )
        self.assertEqual(message_response.status_code, 200)

        session_id = message_response.json()["session_id"]
        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )
        content = b"".join(stream_response.streaming_content).decode("utf-8")

        self.assertEqual(
            _collect_stream_chunks(content),
            "올바른 질문이 아닙니다.",
        )

    def test_message_answers_account_question(self) -> None:
        message_response = self.client.post(
            self.messages_url,
            data={"message": "회원가입은 어떻게 하나요?"},
            format="json",
        )
        self.assertEqual(message_response.status_code, 200)

        session_id = message_response.json()["session_id"]
        stream_response = self.client.get(
            self.stream_url,
            data={"session_id": session_id},
        )
        content = b"".join(stream_response.streaming_content).decode("utf-8")

        self.assertEqual(
            _collect_stream_chunks(content),
            "회원가입은 아이디, 비밀번호, 이름, 닉네임, 성별 등 필수 정보를 입력해 진행할 수 있습니다.",
        )

    def test_account_knowledge_includes_id_and_password_help(self) -> None:
        self.assertEqual(
            build_answer("아이디 찾기는 어떻게 하나요?"),
            "아이디 찾기는 가입한 계정 정보를 확인하는 기능입니다. 화면에서 요구하는 본인 확인 절차를 진행해 주세요.",
        )
        self.assertEqual(
            build_answer("비밀번호를 잊어버렸어요"),
            "비밀번호를 잊은 경우 비밀번호 찾기 또는 재설정 기능을 통해 새 비밀번호로 변경할 수 있습니다.",
        )

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

    def test_stream_fail_when_session_id_missing(self) -> None:
        response = self.client.get(self.stream_url)

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
