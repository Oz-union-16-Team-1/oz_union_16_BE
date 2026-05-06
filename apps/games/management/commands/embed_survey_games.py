from django.core.management.base import BaseCommand

from apps.survey.services.survey_recommendation import SurveyGameEmbeddingService


class Command(BaseCommand):
    help = "설문 추천용 게임 벡터를 생성합니다."

    def add_arguments(self, parser):
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--all", action="store_true")
        parser.add_argument(
            "--all-candidates",
            action="store_true",
            help="설문 임베딩 조건에 맞는 모든 게임을 처리합니다.",
        )

    def handle(self, *args, **options):
        service = SurveyGameEmbeddingService()
        limit = None if options["all_candidates"] else options["limit"]
        result = service.sync_embeddings(
            offset=options["offset"],
            limit=limit,
            only_missing=not options["all"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"embedded survey games: {result['count']} (failed: {result['failed']})"
            )
        )
