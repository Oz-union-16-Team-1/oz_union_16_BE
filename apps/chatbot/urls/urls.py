from django.urls import path

from apps.chatbot.views.chatbot_views import (
    ChatbotMessageAPIView,
    ChatbotSessionStatusAPIView,
    ChatbotStreamAPIView,
)

urlpatterns = [
    path("messages", ChatbotMessageAPIView.as_view(), name="chatbot-messages"),
    path("messages/", ChatbotMessageAPIView.as_view(), name="chatbot-messages-slash"),
    path("stream", ChatbotStreamAPIView.as_view(), name="chatbot-stream"),
    path("stream/", ChatbotStreamAPIView.as_view(), name="chatbot-stream-slash"),
    path(
        "sessions/<uuid:session_id>",
        ChatbotSessionStatusAPIView.as_view(),
        name="chatbot-session-status",
    ),
    path(
        "sessions/<uuid:session_id>/",
        ChatbotSessionStatusAPIView.as_view(),
        name="chatbot-session-status-slash",
    ),
]
