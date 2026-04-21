# IGDB Core 공통 조회 함수 가이드

## 대상
- 파일: `apps/core/igdb.py`
- 함수:
  - `query_games_raw(query: str)`
  - `query_games(*, fields, where, sort=None, limit=500, offset=0)`

## 1) query_games 파라미터

- `fields`:
  - IGDB `fields` 절
  - 예: `id,name,genres,themes,videos.video_id,cover.url,total_rating,total_rating_count,first_release_date,summary,storyline`
- `where`:
  - IGDB `where` 절
  - 예: `platforms = (6) & total_rating != null & total_rating_count > 30`
- `sort`:
  - 정렬 절
  - 예: `total_rating desc`
- `limit`:
  - 페이지 크기
  - 기본값: `500`
- `offset`:
  - 페이지 시작 위치
  - 기본값: `0`

## 2) 반환값 / 오류 처리

- 성공:
  - IGDB JSON 응답(list/dict) 그대로 반환
- 실패(네트워크/타임아웃/HTTP 에러):
  - 로그 기록 후 `None` 반환
- 참고:
  - `query_games`는 쿼리 문자열을 조합해 `query_games_raw`를 호출하는 래퍼 함수

## 3) 사용 예시 

```python
from apps.core import igdb_client

rows = igdb_client.query_games(
    fields="id,name,genres,themes,cover.url,total_rating,total_rating_count,first_release_date,summary,storyline,videos.video_id",
    where="platforms = (6) & total_rating != null & total_rating_count > 30",
    sort="first_release_date desc",
    limit=100,
    offset=0,
)

if rows is None:
    # 외부 연동 장애 처리 (503 등)
    ...
else:
    # rows 후처리
    ...
```

## 4) raw 쿼리 예시

```python
raw_query = (
    "fields id,name,total_rating; "
    "where platforms = (6) & total_rating != null; "
    "sort total_rating desc; "
    "limit 50; offset 0;"
)
rows = igdb_client.query_games_raw(raw_query)
```