COMPOSE := docker compose -f docker-compose.local.yml --env-file envs/.local.env

.PHONY: build up down restart logs ps \
        migrate makemigrations createsuperuser shell \
        db-shell redis-cli lint code_format test prune help

build:  ## 이미지 빌드
	$(COMPOSE) build

up:  ## 컨테이너 백그라운드 실행
	$(COMPOSE) up -d

down:  ## 컨테이너 중지 & 제거
	$(COMPOSE) down

restart:  ## 컨테이너 재시작
	$(COMPOSE) down
	$(COMPOSE) up -d

logs:  ## 로그 실시간 확인
	$(COMPOSE) logs -f

ps:  ## 컨테이너 상태 확인
	$(COMPOSE) ps

migrate:  ## 마이그레이션 실행
	$(COMPOSE) exec django uv run python manage.py migrate

makemigrations:  ## 마이그레이션 파일 생성
	$(COMPOSE) exec django uv run python manage.py makemigrations

createsuperuser:  ## 관리자 계정 생성
	$(COMPOSE) exec django uv run python manage.py createsuperuser

shell:  ## Django shell 접속
	$(COMPOSE) exec django uv run python manage.py shell

lint:  ## ruff 코드 검사
	$(COMPOSE) exec django uv run ruff check .
	$(COMPOSE) exec django uv run ruff format --check .

code_format:  ## isort black 코드 포메팅
	$(COMPOSE) exec django uv run isort .
	$(COMPOSE) exec django uv run black .

test:  ## mypy 타입체크 + Django 테스트
	$(COMPOSE) exec django uv run mypy .
	$(COMPOSE) exec django uv run python manage.py test apps


db-shell:  ## PostgreSQL 직접 접속
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-template_db}

redis-cli:  ## Redis CLI 접속
	$(COMPOSE) exec redis redis-cli

prune:  ## 안 쓰는 이미지/볼륨 전부 정리
	docker system prune -f
	docker volume prune -f

help:  ## 사용 가능한 명령어 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help