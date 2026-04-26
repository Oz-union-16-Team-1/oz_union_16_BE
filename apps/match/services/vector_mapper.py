from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.games.models import Game
from apps.match.constants import (
    MATCH_VECTOR_DEFAULTS,
    MATCH_VECTOR_DIM,
    MATCH_VECTOR_GENRE_AXIS_WEIGHTS,
    MATCH_VECTOR_INDEX,
    MATCH_VECTOR_MOOD_AXIS_WEIGHTS,
    MATCH_VECTOR_POPULARITY_DEFAULT,
    MATCH_VECTOR_POPULARITY_FIELD,
    MATCH_VECTOR_POPULARITY_SCALE,
    MATCH_VECTOR_TAG_FIELDS,
    PGTI_GENRE_MATCH_RULES,
)


@dataclass(frozen=True)
class VectorMappingResult:
    vector: list[float]
    pgti_genre_ids: list[int]


class MatchVectorMapper:
    def map_game(self, game: Game) -> VectorMappingResult:
        tag_sets = self._build_tag_sets(game)
        vector = [0.0] * MATCH_VECTOR_DIM

        self._apply_genre_axes(vector, tag_sets)
        self._apply_mood_axes(vector, tag_sets)

        popularity = self._normalize_popularity(
            getattr(game, MATCH_VECTOR_POPULARITY_FIELD, None)
        )
        vector[MATCH_VECTOR_INDEX["popularity"]] = popularity

        pgti_genre_ids = self._extract_pgti_genres(tag_sets)
        return VectorMappingResult(vector=vector, pgti_genre_ids=pgti_genre_ids)

    def _build_tag_sets(self, game: Game) -> dict[str, set[int]]:
        return {
            field: self._extract_ids(getattr(game, field, None))
            for field in MATCH_VECTOR_TAG_FIELDS
        }

    def _extract_ids(self, raw: Any) -> set[int]:
        if raw is None:
            return set()

        ids: set[int] = set()

        if isinstance(raw, list):
            for item in raw:
                self._add_id(ids, item)
            return ids

        if isinstance(raw, dict):
            if "id" in raw:
                self._add_id(ids, raw.get("id"))
            values = raw.get("ids")
            if isinstance(values, list):
                for item in values:
                    self._add_id(ids, item)
            return ids

        self._add_id(ids, raw)
        return ids

    def _add_id(self, ids: set[int], value: Any) -> None:
        if isinstance(value, bool):
            return

        if isinstance(value, int):
            ids.add(value)
            return

        if isinstance(value, str) and value.isdigit():
            ids.add(int(value))
            return

        if isinstance(value, dict) and "id" in value:
            nested = value.get("id")
            if isinstance(nested, int):
                ids.add(nested)
            elif isinstance(nested, str) and nested.isdigit():
                ids.add(int(nested))

    def _apply_genre_axes(
        self, vector: list[float], tag_sets: dict[str, set[int]]
    ) -> None:
        for axis_name, field_rules in MATCH_VECTOR_GENRE_AXIS_WEIGHTS.items():
            idx = MATCH_VECTOR_INDEX[axis_name]
            values: list[float] = []

            for field, weight_map in field_rules.items():
                tag_ids = tag_sets.get(field, set())
                for tag_id, weight in weight_map.items():
                    if tag_id in tag_ids:
                        values.append(weight)

            vector[idx] = max(values) if values else 0.0

    def _apply_mood_axes(
        self, vector: list[float], tag_sets: dict[str, set[int]]
    ) -> None:
        for axis_name, field_rules in MATCH_VECTOR_MOOD_AXIS_WEIGHTS.items():
            idx = MATCH_VECTOR_INDEX[axis_name]
            values: list[float] = []

            for field, weight_map in field_rules.items():
                tag_ids = tag_sets.get(field, set())
                for tag_id, weight in weight_map.items():
                    if tag_id in tag_ids:
                        values.append(weight)

            if values:
                avg = sum(values) / len(values)
                vector[idx] = self._clamp(avg, -1.0, 1.0)
            else:
                vector[idx] = MATCH_VECTOR_DEFAULTS.get(axis_name, 0.0)

    def _normalize_popularity(self, rating: Any) -> float:
        if rating is None:
            return MATCH_VECTOR_POPULARITY_DEFAULT

        try:
            value = float(rating)
        except TypeError:
            return MATCH_VECTOR_POPULARITY_DEFAULT
        except ValueError:
            return MATCH_VECTOR_POPULARITY_DEFAULT

        normalized = value / MATCH_VECTOR_POPULARITY_SCALE
        return self._clamp(normalized, 0.0, 1.0)

    def _extract_pgti_genres(self, tag_sets: dict[str, set[int]]) -> list[int]:
        genres = tag_sets.get("genres", set())
        themes = tag_sets.get("themes", set())
        matched: set[int] = set()

        for pgti_genre_id, rule in PGTI_GENRE_MATCH_RULES.items():
            rule_genres = set(rule.get("genres", ()))
            rule_themes = set(rule.get("themes", ()))

            if (rule_genres & genres) or (rule_themes & themes):
                matched.add(pgti_genre_id)

        return sorted(matched)

    def _clamp(self, value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))
