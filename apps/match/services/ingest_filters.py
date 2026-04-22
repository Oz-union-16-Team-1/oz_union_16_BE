# apps/match/services/ingest_filters.py
from __future__ import annotations

from collections import Counter
from typing import Any

from apps.match.constants import (
    MATCH_INGEST_ALLOWED_CATEGORIES,
    MATCH_INGEST_MIN_AGG_RATING,
    MATCH_INGEST_MIN_RATING,
    MATCH_INGEST_MIN_RATING_COUNT,
    MATCH_INGEST_MIN_RELEASE_TS,
    MATCH_INGEST_REQUIRED_PLATFORM,
    MATCH_INGEST_REQUIRED_STATUS,
)


ALLOWED_CATEGORIES = set(MATCH_INGEST_ALLOWED_CATEGORIES)
ALLOWED_STATUS = {MATCH_INGEST_REQUIRED_STATUS}
PC_PLATFORM_ID = MATCH_INGEST_REQUIRED_PLATFORM


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _as_set(value: Any) -> set[int]:
    if not value or not isinstance(value, list):
        return set()

    out: set[int] = set()
    for v in value:
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            out.add(v)
            continue
        if isinstance(v, float) and v.is_integer():
            out.add(int(v))
            continue
        if isinstance(v, str):
            text = v.strip()
            if text.isdigit():
                out.add(int(text))
    return out


def _has_description(game: dict[str, Any]) -> bool:
    summary = (game.get("summary") or "").strip()
    storyline = (game.get("storyline") or "").strip()
    return bool(summary or storyline)


def _valid_aggregated_rating(game: dict[str, Any]) -> bool:
    # aggregated_rating이 None이면 통과(인디 게임 구제)
    agg = game.get("aggregated_rating")
    if agg is None:
        return True
    try:
        return float(agg) >= MATCH_INGEST_MIN_AGG_RATING
    except TypeError:
        return False
    except ValueError:
        return False


def _valid_rating(game: dict[str, Any]) -> bool:
    try:
        rating_count = int(game.get("rating_count") or 0)
        rating = float(game.get("rating") or 0)
    except TypeError:
        return False
    except ValueError:
        return False

    return (
        rating_count >= MATCH_INGEST_MIN_RATING_COUNT
        and rating >= MATCH_INGEST_MIN_RATING
    )


def _valid_release_ts(game: dict[str, Any]) -> bool:
    # IGDB first_release_date: unix timestamp
    ts = game.get("first_release_date")
    if ts is None:
        return False
    try:
        return int(ts) >= MATCH_INGEST_MIN_RELEASE_TS
    except TypeError:
        return False
    except ValueError:
        return False


def _valid_platform(game: dict[str, Any]) -> bool:
    # PC(id=6) 포함이면 통과
    platforms = _as_set(game.get("platforms"))
    return PC_PLATFORM_ID in platforms


def _valid_category(game: dict[str, Any]) -> bool:
    category = _to_int(game.get("category"))
    return category is not None and category in ALLOWED_CATEGORIES


def _valid_status(game: dict[str, Any]) -> bool:
    status = _to_int(game.get("status"))
    return status is not None and status in ALLOWED_STATUS


def _valid_completeness(game: dict[str, Any]) -> bool:
    genres_ok = bool(game.get("genres"))
    videos_ok = bool(game.get("videos"))
    release_ok = game.get("first_release_date") is not None
    description_ok = _has_description(game)
    return genres_ok and videos_ok and release_ok and description_ok


def validate_game(game: dict[str, Any]) -> str | None:
    """
    통과면 None, 탈락이면 reason 문자열 반환.
    reason은 배치 통계(excluded_reasons)와 운영 로그에서 그대로 사용한다.
    """
    if not _valid_category(game):
        return "invalid_category"
    if not _valid_status(game):
        return "invalid_status"
    if not _valid_rating(game):
        return "low_rating_or_count"
    if not _valid_aggregated_rating(game):
        return "low_aggregated_rating"
    if not _valid_completeness(game):
        return "incomplete_data"
    if not _valid_platform(game):
        return "platform_not_pc"
    if not _valid_release_ts(game):
        return "too_old_release_or_missing"
    return None


def filter_games_with_reasons(
    games: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    passed: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()

    for game in games:
        reason = validate_game(game)
        if reason is None:
            passed.append(game)
        else:
            reasons[reason] += 1

    return passed, dict(reasons)
