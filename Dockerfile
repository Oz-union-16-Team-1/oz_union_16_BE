# 1. uv 바이너리를 가져오기 위한 멀티 스테이지 빌드 활용
FROM ghcr.io/astral-sh/uv:latest AS uv_bin
FROM python:3.14-rc-slim

# 작업 디렉토리 설정
WORKDIR /oz_union_16_BE

# uv 바이너리 복사 (설치 과정 생략으로 빌드 속도 향상)
COPY --from=uv_bin /uv /uvx /bin/

# 시스템 패키지 설치 (필요한 경우만)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 환경 변수 설정: .venv를 만들지 않고 시스템 환경에 바로 설치 (Docker 컨테이너 특성 활용)
ENV UV_PROJECT_ENVIRONMENT="/usr/local"
ENV UV_COMPILE_BYTECODE=1

# 의존성 파일 먼저 복사 (캐싱 활용)
COPY pyproject.toml uv.lock ./

# 의존성 설치
# --no-install-project: 프로젝트 자체는 설치하지 않고 라이브러리만 먼저 설치
RUN uv sync --frozen --no-install-project --no-dev

# 프로젝트 소스 복사
COPY . .

# (선택 사항) 프로젝트 자체 설치
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "config.wsgi:application"]