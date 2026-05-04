from django.urls import path

from apps.chatbot.views.chatbot_views import (
    ChatbotMessageAPIView,
    ChatbotSessionStatusAPIView,
    ChatbotStreamAPIView,
)

urlpatterns = [
    path("messages", ChatbotMessageAPIView.as_view(), name="chatbot-messages"),
    path("stream", ChatbotStreamAPIView.as_view(), name="chatbot-stream"),
    path(
        "sessions/<uuid:session_id>",
        ChatbotSessionStatusAPIView.as_view(),
        name="chatbot-session-status",
    ),
]
