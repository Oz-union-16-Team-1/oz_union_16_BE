from apps.chatbot.services.chatbot_faq_answers import (
    DEFAULT_IN_SCOPE_ANSWER,
    FAQ_ANSWERS,
)
from apps.chatbot.services.chatbot_filter_rules import OUT_OF_SCOPE_ANSWER
from apps.chatbot.services.chatbot_intent_classifier import classify_intent
from apps.chatbot.services.chatbot_suggestion_rules import (
    DEFAULT_SUGGESTED_QUESTIONS,
    SUGGESTIONS_BY_INTENT,
)


def build_answer(message: str) -> str:
    intent = classify_intent(message)

    if intent == "OUT_OF_SCOPE":
        return OUT_OF_SCOPE_ANSWER

    if intent is None or intent == "IN_SCOPE_UNKNOWN":
        return DEFAULT_IN_SCOPE_ANSWER

    return FAQ_ANSWERS.get(intent, DEFAULT_IN_SCOPE_ANSWER)


def build_suggested_questions(message: str) -> list[str]:
    intent = classify_intent(message)

    if intent in (None, "OUT_OF_SCOPE"):
        return []

    questions = SUGGESTIONS_BY_INTENT.get(intent, DEFAULT_SUGGESTED_QUESTIONS)
    return _exclude_current_question(questions, message)


def _exclude_current_question(
    questions: tuple[str, ...], message: str
) -> list[str]:
    return [
        question
        for question in questions
        if _normalize_question_text(question)
        != _normalize_question_text(message)
    ]


def _normalize_question_text(text: str) -> str:
    removable_chars = " ?!.,~요죠까나요습니까"
    normalized = text.strip().lower()
    for char in removable_chars:
        normalized = normalized.replace(char, "")
    return normalized
