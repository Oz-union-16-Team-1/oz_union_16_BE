from apps.chatbot.services.chatbot_filter_rules import (
    BLOCKED_SCOPE_KEYWORDS,
    DEFAULT_SUGGESTED_QUESTIONS,
    OUT_OF_SCOPE_ANSWER,
    SITE_KNOWLEDGE_BASE,
    SITE_SCOPE_KEYWORDS,
    SUGGESTED_QUESTION_RULES,
)


def build_answer(message: str) -> str:
    normalized = message.strip()
    lowered = normalized.lower()

    if any(keyword in lowered for keyword in BLOCKED_SCOPE_KEYWORDS):
        return OUT_OF_SCOPE_ANSWER

    if not any(keyword in lowered for keyword in SITE_SCOPE_KEYWORDS):
        return OUT_OF_SCOPE_ANSWER

    for knowledge in SITE_KNOWLEDGE_BASE:
        if all(keyword in lowered for keyword in knowledge["keywords"]):
            return knowledge["answer"]

    return (
        "우리 사이트는 게임 설문조사로 취향을 파악해 게임을 추천하고, 좋아요/찜과 별점으로 "
        "관심 게임과 인기 TOP100을 확인할 수 있는 서비스입니다. 설문, 추천, 취향, 좋아요, 별점, "
        "인기 TOP100 중 궁금한 내용을 조금 더 구체적으로 입력해 주세요."
    )


def build_suggested_questions(message: str) -> list[str]:
    lowered = message.strip().lower()

    if any(keyword in lowered for keyword in BLOCKED_SCOPE_KEYWORDS):
        return []

    for rule in SUGGESTED_QUESTION_RULES:
        if all(keyword in lowered for keyword in rule["keywords"]):
            return _exclude_current_question(rule["questions"], lowered)

    if any(keyword in lowered for keyword in SITE_SCOPE_KEYWORDS):
        return _exclude_current_question(DEFAULT_SUGGESTED_QUESTIONS, lowered)

    return []


def _exclude_current_question(
    questions: tuple[str, ...], lowered_message: str
) -> list[str]:
    return [
        question
        for question in questions
        if _normalize_question_text(question)
        != _normalize_question_text(lowered_message)
    ]


def _normalize_question_text(text: str) -> str:
    removable_chars = " ?!.,~요죠까나요습니까"
    normalized = text.strip().lower()
    for char in removable_chars:
        normalized = normalized.replace(char, "")
    return normalized
