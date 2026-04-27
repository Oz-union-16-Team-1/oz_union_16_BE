from __future__ import annotations

from dataclasses import dataclass

from apps.games.models import Game
from apps.match.models import MatchGameGenreMap, MatchGamePreference
from apps.match.services.vector_mapper import MatchVectorMapper


@dataclass
class VectorSyncStats:
    scanned: int = 0
    upserted_preferences: int = 0
    upserted_genre_links: int = 0


class MatchVectorSyncService:
    def __init__(self) -> None:
        self.mapper = MatchVectorMapper()

    def run(self) -> VectorSyncStats:
        stats = VectorSyncStats()

        for game in Game.objects.all().order_by("game_id").iterator(chunk_size=500):
            stats.scanned += 1
            mapped = self.mapper.map_game(game)

            MatchGamePreference.objects.update_or_create(
                game_id=game,
                defaults={"game_preference_vector": mapped.vector},
            )
            stats.upserted_preferences += 1

            MatchGameGenreMap.objects.filter(game_id=game).delete()
            objs = [
                MatchGameGenreMap(game_id=game, igdb_genre_id=genre_id)
                for genre_id in mapped.pgti_genre_ids
            ]
            if objs:
                MatchGameGenreMap.objects.bulk_create(objs)
                stats.upserted_genre_links += len(objs)

        return stats
