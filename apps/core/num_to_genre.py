from apps.core.igdb import IGDB


def num_to_genre(num: int) -> str | None:
    return IGDB.GENRE_NAME_MAP.get(num)
