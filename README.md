# PGTI Backend

## 프로젝트 소개

> PGTI는 사용자의 게임 취향을 분석해 개인화된 게임을 추천하는 서비스입니다.
> 회원가입과 소셜 로그인, 인기 게임 조회, 게임 상세 정보, 좋아요, AI 설문 추천,
> 장르 기반 매칭 추천, 고객센터용 챗봇까지 게임 추천 경험에 필요한 백엔드 API를 제공합니다.
>
> 이 저장소는 PGTI 서비스의 Django 기반 백엔드 API, 관리자 페이지, 추천/설문/챗봇 기능을 담당합니다.

---

## 팀 동료

| <a href="https://github.com/pcw8233"><img src="https://github.com/pcw8233.png" width="100px"><br><sub><b>@pcw8233</b></sub></a> | <a href="https://github.com/jun2k5"><img src="https://github.com/jun2k5.png" width="100px"><br><sub><b>@jun2k5</b></sub></a> | <a href="https://github.com/wooryun"><img src="https://github.com/wooryun.png" width="100px"><br><sub><b>@wooryun</b></sub></a> | <a href="https://github.com/Justman-yzz"><img src="https://github.com/Justman-yzz.png" width="100px"><br><sub><b>@Justman-yzz</b></sub></a> | <a href="https://github.com/dodzn89-cell"><img src="https://github.com/dodzn89-cell.png" width="100px"><br><sub><b>@dodzn89-cell</b></sub></a> |
|:---:|:---:|:---:|:---:|:---:|
| 박철우 | 김병준 | 고건 | 김태준 | 정상운 |
| 팀장 | 팀원 | 팀원 | 팀원 | 팀원 |
| games | users | survey | match | Django Admin, 시스템 챗봇 |

---

## 배포 링크

> ### [백엔드 배포 링크](http://oz-pgti.duckdns.org)
> ### [프론트엔드 배포 링크](https://oz-union-16-fe.vercel.app/)

---

## 프로젝트 발표 영상 & 발표 문서

> ### 2026.04.02 - 2026.05.08
> ### [발표 영상 추가 예정]()
> ### [발표 문서 추가 예정]()

---

## 서비스 소개

| 회원관리 | 게임 조회 | 개인화 추천 |
|:---:|:---:|:---:|
| 일반 회원가입, 로그인, 로그아웃, JWT 갱신, 회원 탈퇴, 내 정보 조회/수정, 비밀번호 변경을 제공합니다. | 인기 TOP 100 게임 목록, 장르/검색 필터, 게임 상세 정보, 좋아요, 운영 대시보드를 제공합니다. | AI 설문 기반 추천과 장르 선택 후 별점 평가 기반 추천 결과를 제공합니다. |

| 소셜 로그인 | 프로필/이미지 | 챗봇 |
|:---:|:---:|:---:|
| Kakao, Naver, Google OAuth2 로그인 및 콜백 처리를 제공합니다. | S3 Presigned URL 발급, 프로필 이미지 등록, 좋아요한 게임 목록 조회를 제공합니다. | 비회원도 사용할 수 있는 FAQ 챗봇 메시지 API와 SSE 스트리밍 API를 제공합니다. |

---

## 사용 스택

### System Architecture

```text
Client
  |
Nginx
  |
Django REST Framework API
  |-- PostgreSQL + pgvector
  |-- Redis
  |-- AWS S3
  |-- IGDB API
  |-- Gemini API
```

### BE

<div align="center">
  <img src="https://img.shields.io/badge/Python_3.14-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Django_6.0-092E20?style=for-the-badge&logo=django&logoColor=white">
  <img src="https://img.shields.io/badge/DRF-A30000?style=for-the-badge&logo=django&logoColor=white">
  <br>
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white">
  <img src="https://img.shields.io/badge/pgvector-336791?style=for-the-badge&logo=postgresql&logoColor=white">
  <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white">
  <br>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white">
  <img src="https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white">
  <img src="https://img.shields.io/badge/Gunicorn-499848?style=for-the-badge&logo=gunicorn&logoColor=white">
  <br>
  <img src="https://img.shields.io/badge/AWS_S3-569A31?style=for-the-badge&logo=amazons3&logoColor=white">
  <img src="https://img.shields.io/badge/Swagger_UI-85EA2D?style=for-the-badge&logo=swagger&logoColor=black">
  <img src="https://img.shields.io/badge/Simple_JWT-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white">
</div>

### Quality

<div align="center">
  <img src="https://img.shields.io/badge/black-000000?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/isort-EF8336?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/mypy-2A6DB2?style=for-the-badge&logo=python&logoColor=white">
</div>

---

## 프로젝트 구조

```text
apps/
  chatbot/  # 비회원 챗봇 메시지, SSE 스트리밍, 세션 상태
  core/     # 공통 유틸, 예외 처리, IGDB 연동, Admin 브랜드 설정
  games/    # 게임 목록/상세/좋아요, 게임 운영 대시보드
  match/    # 장르 선택 및 별점 기반 게임 매칭
  survey/   # AI 설문 세션, 설문 대화, 설문 기반 추천
  users/    # 회원, 인증, 소셜 로그인, 프로필, 좋아요 목록
config/
  settings/ # base/dev/prod 설정
  urls.py   # API 라우팅 및 Swagger 스키마
nginx/      # Nginx dev/local/prod 설정
envs/       # 로컬 환경 변수 파일
```

---

## 로컬 실행

### 1. 환경 변수 준비

로컬 실행 시 `docker-compose.local.yml`은 `envs/.local.env`를 사용합니다.
프로젝트 실행에 필요한 값은 팀 내부 공유 문서를 기준으로 준비합니다.

```bash
mkdir -p envs
```

### 2. 서버 실행

```bash
docker compose -f docker-compose.local.yml up -d --build
```

로컬 접속 주소:

- API 서버: `http://localhost:8000`
- Nginx 경유: `http://localhost`
- Admin: `http://localhost:8000/admin/`
- Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`
- OpenAPI Schema: `http://localhost:8000/api/schema/`

### 3. 서버 종료

```bash
docker compose -f docker-compose.local.yml down
```

---

## 주요 API

### Accounts

Base URL: `/api/v1/accounts/`

- `POST /signup`: 회원가입
- `POST /login`: 로그인
- `POST /logout`: 로그아웃
- `POST /token/refresh`: Access Token 재발급
- `POST /check-id`: 아이디 중복 확인
- `POST /check-nickname`: 닉네임 중복 확인
- `GET /me`: 내 정보 조회
- `PATCH /me`: 내 정보 수정
- `DELETE /me`: 회원 탈퇴
- `POST /me/check-password`: 비밀번호 확인
- `POST /me/change-password`: 비밀번호 변경
- `GET /me/game-like`: 좋아요한 게임 목록
- `POST /me/profile-image/presigned-url`: 프로필 이미지 Presigned URL 발급
- `PUT /me/profile-image`: 프로필 이미지 등록
- `GET /me/social`: 소셜 유저 여부 확인
- `GET /social-login/kakao`: Kakao 소셜 로그인 시작
- `GET /social-login/naver`: Naver 소셜 로그인 시작
- `GET /social-login/google`: Google 소셜 로그인 시작
- `GET /social-login/{provider}/callback`: 소셜 로그인 콜백

### Games

Base URL: `/api/v1/games/`

- `GET /list/top100`: 인기 TOP 100 게임 목록 조회
- `GET /list/{game_id}`: 게임 상세 조회
- `POST /{game_id}/like`: 게임 좋아요
- `DELETE /{game_id}/like`: 게임 좋아요 취소
- `GET /{game_id}/dashboard`: 게임 운영 대시보드

### Survey

Base URL: `/api/v1/survey/`

- `POST /chatbot/sessions`: 설문 세션 시작
- `POST /chatbot/sessions/reset`: 설문 초기화
- `POST /chatbot/sessions/{session_id}/messages`: 설문 챗봇 대화 진행
- `GET /chatbot/sessions/{session_id}/recommendations`: 설문 추천 결과 조회

### Match

Base URL: `/api/v1/match/`

- `GET /genres/image-url`: 매칭 장르별 대표 이미지 조회
- `GET /candidates`: 장르 기반 평가 대상 게임 목록 조회
- `POST /responses`: 매칭 레이팅 제출
- `GET /responses/result`: 매칭 추천 결과 조회

### Chatbot

Base URL: `/api/v1/chatbot/`

- `POST /messages`: FAQ 챗봇 메시지 전송
- `GET /stream`: FAQ 챗봇 SSE 스트리밍
- `GET /sessions/{session_id}`: 챗봇 세션 상태 조회

---

## 프로젝트 규칙

### Branch Strategy

> - `main` / `dev` 브랜치 기본 생성
> - `main`과 `dev` 브랜치 직접 push 제한
> - PR 전 최소 1인 이상 승인 필수

### Git Convention

> 1. 적절한 커밋 접두사 작성
> 2. 커밋 메시지 내용 작성
> 3. 내용 뒤에 이슈 번호를 `#이슈번호` 형식으로 연결

| 접두사 | 설명 |
| --- | --- |
| Feat | 새로운 기능 구현 |
| Add | 에셋 파일 추가 |
| Fix | 버그 수정 |
| Docs | 문서 추가 및 수정 |
| Style | 스타일링 작업 |
| Refactor | 코드 리팩토링 |
| Test | 테스트 |
| Deploy | 배포 |
| Conf | 빌드, 환경 설정 |
| Chore | 기타 작업 |

### Pull Request

> ### Title
> - 제목은 `[Feat] 홈 페이지 구현`과 같이 작성합니다.

> ### PR Type
> - [ ] FEAT: 새로운 기능 구현
> - [ ] ADD: 에셋 파일 추가
> - [ ] FIX: 버그 수정
> - [ ] DOCS: 문서 추가 및 수정
> - [ ] STYLE: 포맷팅 변경
> - [ ] REFACTOR: 코드 리팩토링
> - [ ] TEST: 테스트 관련
> - [ ] DEPLOY: 배포 관련
> - [ ] CONF: 빌드, 환경 설정
> - [ ] CHORE: 기타 작업

> ### Description
> - 구체적인 작업 내용을 작성합니다.
> - API 변경, DB 변경, 화면 변경이 있으면 함께 작성합니다.

> ### Discussion
> - 추후 논의할 점을 작성합니다.

### Code Convention

> BE
> - 패키지명은 전체 소문자 사용
> - 클래스명과 인터페이스명은 CamelCase 사용
> - 클래스 이름은 명사 사용
> - 상수명은 SNAKE_CASE 사용
> - Controller, Service, DTO, Repository 계층별 접미사 통일
> - CRUD 메서드는 `create`, `update`, `find`, `delete` 계열로 통일
> - Test 클래스는 접미사로 `Test` 사용
> - Python 코드는 `black`, `isort`, `mypy` 기준을 따름

> FE
> - styled-components 변수명은 `S` + 변수명 형태 사용
> - styled-components는 return문 위에 작성
> - 이벤트 핸들러는 `handle~` 형태 사용
> - 기본 export는 `export default` 사용
> - 화살표 함수 사용

### Communication Rules

> - Discord 활용
> - 정기 회의 진행
> - API 변경 사항은 명세서와 PR에 함께 기록

---

## 품질 검사

컨테이너 내부에서 아래 명령으로 포맷팅과 타입 검사를 실행합니다.

```bash
docker exec pgti_django black .
docker exec pgti_django isort .
docker exec pgti_django mypy .
docker exec pgti_django python manage.py check
```

`mypy` 실행 시 `types-requests`가 없다면 dev dependency를 동기화합니다.

```bash
docker exec pgti_django uv sync --frozen --group dev
```

---

## Documents

> [API 명세서](https://docs.google.com/spreadsheets/d/1t5-N2UagMHkSlAh0EDdIFAy9Rw50YANsPAwtmFKIO24/edit?gid=0#gid=0)
>
> [요구사항 정의서](https://docs.google.com/spreadsheets/d/15xdRQQAxHQuG0IHL9FNqa-gkL7mvtJbWtkOYCG9p0yA/edit?gid=428803499#gid=428803499)
>
> [테이블 명세서](https://docs.google.com/spreadsheets/d/1tRDH3Ek6puT4LioW3XtGh8wEiVZOrX6AQ45mApxQknA/edit?gid=0#gid=0)
>

