from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


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
        self.max_retries: int = settings.IGDB_MAX_RETRIES
        self.retry_delay: float = settings.IGDB_RETRY_DELAY
        self.request_interval: float = settings.IGDB_REQUEST_INTERVAL

    def _request_json(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Any:
        req = Request(url=url, data=body, headers=headers or {}, method=method)
        last_error: Exception | None = None

        # Transient 오류(429/5xx, network)는 재시도하고, 그 외는 즉시 실패 처리.
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(req, timeout=self.timeout) as res:
                    raw = res.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or 500 <= exc.code < 600:
                    last_error = IgdbRequestError(f"IGDB HTTP {exc.code}: {detail}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                raise IgdbRequestError(f"IGDB HTTP {exc.code}: {detail}") from exc
            except URLError as exc:
                last_error = IgdbRequestError(f"IGDB 연결 오류: {exc.reason}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise IgdbRequestError(f"IGDB 연결 오류: {exc.reason}") from exc

        raise last_error if last_error else IgdbRequestError("IGDB 요청 실패")

    def get_access_token(self) -> str:
        # 배치 실행마다 1회 발급해서 페이지 수집에 재사용
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
        self, *, access_token: str, query: str
    ) -> list[dict[str, Any]]:
        # IGDB games endpoint는 APICALYPSE query(text/plain)를 POST body로
        body = query.encode("utf-8")
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

        # 이 단계에서는 list 형태만 보장하고, 상세 필드 검증은 필터 파이프라인에서 처리.
        if not isinstance(payload, list):
            raise IgdbRequestError("IGDB games 응답 형식이 올바르지 않습니다.")
        return payload
