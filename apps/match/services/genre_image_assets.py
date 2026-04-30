from __future__ import annotations

from typing import Any, Literal, TypedDict

from apps.core.igdb import igdb_client


class ImageOption(TypedDict):
    url: str
    source: Literal["cover", "screenshot", "artwork"]
    label: str


def normalize_image_url(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    url = raw.strip()
    if not url:
        return None

    if url.startswith("//"):
        url = f"https:{url}"

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://images.igdb.com/igdb/image/upload/t_1080p/{url}.jpg"

    return url.replace("t_thumb", "t_1080p")


def image_id_to_url(image_id: str) -> str:
    return f"https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg"


def merge_unique_image_options(options: list[ImageOption]) -> list[ImageOption]:
    out: list[ImageOption] = []
    seen: set[str] = set()

    for opt in options:
        normalized = normalize_image_url(opt.get("url"))
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(
            ImageOption(
                url=normalized,
                source=opt["source"],
                label=opt["label"],
            )
        )

    return out


def build_cover_option(raw_cover: Any) -> list[ImageOption]:
    url = normalize_image_url(raw_cover)
    if not url:
        return []
    return [ImageOption(url=url, source="cover", label="대표 커버")]


def build_screenshot_options(raw: Any) -> list[ImageOption]:
    if not isinstance(raw, list):
        return []

    out: list[ImageOption] = []
    idx = 1
    for item in raw:
        url: str | None = None

        if isinstance(item, dict):
            image_id = item.get("image_id")
            if isinstance(image_id, str) and image_id.strip():
                url = image_id_to_url(image_id.strip())
            else:
                url = normalize_image_url(item.get("url"))
        elif isinstance(item, str):
            normalized = normalize_image_url(item)
            url = normalized if normalized else image_id_to_url(item.strip())

        if not url:
            continue

        out.append(
            ImageOption(
                url=url,
                source="screenshot",
                label=f"스크린샷 #{idx}",
            )
        )
        idx += 1

    return merge_unique_image_options(out)


def build_artwork_options(raw: Any) -> list[ImageOption]:
    if not isinstance(raw, list):
        return []

    out: list[ImageOption] = []
    idx = 1
    for item in raw:
        url: str | None = None

        if isinstance(item, dict):
            image_id = item.get("image_id")
            if isinstance(image_id, str) and image_id.strip():
                url = image_id_to_url(image_id.strip())
            else:
                url = normalize_image_url(item.get("url"))
        elif isinstance(item, str):
            normalized = normalize_image_url(item)
            url = normalized if normalized else image_id_to_url(item.strip())

        if not url:
            continue

        out.append(
            ImageOption(
                url=url,
                source="artwork",
                label=f"아트워크 #{idx}",
            )
        )
        idx += 1

    return merge_unique_image_options(out)


def fetch_artwork_options_map(
    game_ids: list[int], chunk_size: int = 200
) -> dict[int, list[ImageOption]]:
    unique_ids = sorted(set(game_ids))
    if not unique_ids:
        return {}

    result: dict[int, list[ImageOption]] = {}

    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i : i + chunk_size]
        ids_str = ",".join(str(v) for v in chunk)
        query = (
            "fields id, artworks.image_id, artworks.url; "
            f"where id = ({ids_str}); "
            f"limit {len(chunk)};"
        )

        try:
            rows = igdb_client.query_games_raw(query) or []
        except Exception:
            rows = []

        if not isinstance(rows, list):
            continue

        for row in rows:
            try:
                gid = int(row.get("id") or 0)
            except TypeError, ValueError:
                continue
            if gid <= 0:
                continue

            options = build_artwork_options(row.get("artworks"))
            if not options:
                continue

            prev = result.get(gid, [])
            result[gid] = merge_unique_image_options(prev + options)

    return result
