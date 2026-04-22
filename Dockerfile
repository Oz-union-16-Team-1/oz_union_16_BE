# 1. uv 바이너리 가져오기
FROM ghcr.io/astral-sh/uv:latest AS uv_bin
FROM python:3.14-rc-slim

# 작업 디렉토리 설정
WORKDIR /oz_union_16_BE

# 핵심 환경 변수 설정
# UV_SYSTEM_PYTHON: 가상환경(.venv)을 만들지 않고 /usr/local에 직접 설치하도록 강제
ENV UV_SYSTEM_PYTHON=1
ENV UV_COMPILE_BYTECODE=1
# PYTHONPATH: 앱 루트와 라이브러리 경로를 파이썬이 찾을 수 있게 명시
ENV PYTHONPATH="/oz_union_16_BE:/usr/local/lib/python3.14/site-packages"

# uv 바이너리 복사
COPY --from=uv_bin /uv /uvx /bin/

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사
COPY pyproject.toml uv.lock ./

# [수정] --no-dev와 함께 --frozen을 사용하여 시스템 환경에 동기화
# UV_SYSTEM_PYTHON=1 덕분에 이제 /usr/local에 설치됩니다.
RUN uv sync --frozen --no-dev

# 프로젝트 소스 복사
COPY . .

EXPOSE 8000

# [수정] gunicorn 실행 시에도 경로 문제를 방지하기 위해
# 가급적 uv run을 사용하거나, 정확한 파이썬 환경에서 실행되도록 보장합니다.
CMD ["uv", "run", "gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "config.wsgi:application"]