from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from apps.match.services.igdb_query import build_games_query


class IgdbClientError(Exception):
    pass


class IgdbCredentialsError(IgdbClientError):
    pass


class IgdbAuthError(IgdbClientError):
    pass


class IgdbRequestError(IgdbClientError):
    pass


class IgdbClient:
    def __init__(self) -> None:
        self.client_id: str = settings.IGDB_CLIENT_ID
        self.client_secret: str = settings.IGDB_CLIENT_SECRET
        self.auth_url: str = settings.IGDB_AUTH_URL
        self.games_url: str = settings.IGDB_GAMES_URL
        self.timeout: int = settings.IGDB_REQUEST_TIMEOUT
        self.page_size: int = settings.IGDB_PAGE_SIZE
        self.max_pages: int = settings.IGDB_MAX_PAGES

    def _request_json(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Any:
        req = Request(url=url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as res:
                raw = res.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IgdbRequestError(f"IGDB HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise IgdbRequestError(f"IGDB 연결 오류: {exc.reason}") from exc

        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def get_access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise IgdbCredentialsError(
                "IGDB_CLIENT_ID/IGDB_CLIENT_SECRET가 설정되지 않았습니다."
            )

        query = urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
        )
        payload = self._request_json(
            url=f"{self.auth_url}?{query}",
            method="POST",
            headers={"Accept": "application/json"},
        )

        token = payload.get("access_token")
        if not token:
            raise IgdbAuthError("IGDB access_token 발급에 실패했습니다.")
        return token

    def fetch_games_page(
        self, *, access_token: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        body = build_games_query(limit=limit, offset=offset).encode("utf-8")
        payload = self._request_json(
            url=self.games_url,
            method="POST",
            headers={
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "text/plain",
            },
            body=body,
        )

        if not isinstance(payload, list):
            raise IgdbRequestError("IGDB games 응답 형식이 올바르지 않습니다.")
        return payload

    def iter_games(self) -> Iterator[dict[str, Any]]:
        token = self.get_access_token()
        offset = 0

        for _ in range(self.max_pages):
            rows = self.fetch_games_page(
                access_token=token,
                limit=self.page_size,
                offset=offset,
            )
            if not rows:
                break

            for row in rows:
                yield row

            if len(rows) < self.page_size:
                break

            offset += self.page_size
