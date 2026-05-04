from django.urls import path

from apps.chatbot.views.chatbot_messages_views import ChatbotMessageAPIView
from apps.chatbot.views.chatbot_sessions_views import ChatbotSessionStatusAPIView
from apps.chatbot.views.chatbot_streaming_views import ChatbotStreamAPIView

urlpatterns = [
    path("messages", ChatbotMessageAPIView.as_view(), name="chatbot-messages"),
    path("stream", ChatbotStreamAPIView.as_view(), name="chatbot-stream"),
    path(
        "sessions/<uuid:session_id>",
        ChatbotSessionStatusAPIView.as_view(),
        name="chatbot-session-status",
    ),
]
