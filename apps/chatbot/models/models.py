from django.db import models


class ChatbotSession(models.Model):
    chatbot_sessions_id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chatbot_sessions"
