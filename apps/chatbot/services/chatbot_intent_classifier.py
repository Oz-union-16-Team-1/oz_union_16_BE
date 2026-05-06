from apps.chatbot.services.chatbot_filter_rules import (
    BLOCKED_SCOPE_KEYWORDS,
    SITE_SCOPE_KEYWORDS,
)
from apps.chatbot.services.chatbot_intent_rules import INTENT_RULES


def normalize_message(message: str) -> str:
    return " ".join(message.strip().lower().split())


def classify_intent(message: str) -> str | None:
    normalized = normalize_message(message)
    compact = normalized.replace(" ", "")

    if _contains_any(normalized, compact, BLOCKED_SCOPE_KEYWORDS):
        return "OUT_OF_SCOPE"

    best_intent: str | None = None
    best_score = 0

    for rule in INTENT_RULES:
        for pattern in rule["patterns"]:
            score = _match_score(pattern, normalized, compact)
            if score == 0:
                continue

            total_score = rule["priority"] + score
            if total_score > best_score:
                best_score = total_score
                best_intent = rule["intent"]

    if best_intent is not None:
        return best_intent

    if _contains_any(normalized, compact, SITE_SCOPE_KEYWORDS):
        return "IN_SCOPE_UNKNOWN"

    return "OUT_OF_SCOPE"


def _match_score(
    pattern: str | tuple[str, ...],
    normalized: str,
    compact: str,
) -> int:
    if isinstance(pattern, tuple):
        if all(_contains(normalized, compact, keyword) for keyword in pattern):
            return 20 + len(pattern) * 10
        return 0

    if _contains(normalized, compact, pattern):
        return 30 + min(len(pattern), 30)

    return 0


def _contains_any(
    normalized: str,
    compact: str,
    keywords: tuple[str, ...],
) -> bool:
    return any(_contains(normalized, compact, keyword) for keyword in keywords)


def _contains(normalized: str, compact: str, keyword: str) -> bool:
    normalized_keyword = normalize_message(keyword)
    compact_keyword = normalized_keyword.replace(" ", "")
    return normalized_keyword in normalized or compact_keyword in compact
