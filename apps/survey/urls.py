from django.urls import path

from apps.survey.views.survey_chatbot_message import SurveyChatbotMessageAPIView
from apps.survey.views.survey_chatbot_session import (
    SurveyChatbotSessionCreateAPIView,
    SurveyChatbotSessionResetAPIView,
)

urlpatterns = [
    path(
        "chatbot/sessions/",
        SurveyChatbotSessionCreateAPIView.as_view(),
        name="survey-chatbot-session-create",
    ),
    path(
        "chatbot/sessions/reset/",
        SurveyChatbotSessionResetAPIView.as_view(),
        name="survey-chatbot-session-reset",
    ),
    path(
        "chatbot/sessions/<uuid:session_id>/messages/",
        SurveyChatbotMessageAPIView.as_view(),
        name="survey-chatbot-message",
    ),
]
