from rest_framework import serializers


# Game_List_Top100 API
class GameListTop100Serializer(serializers.Serializer):
    game_id = serializers.IntegerField()  # IGDB ID -> 우리 서비스 식별자
    name = serializers.CharField()  # 게임 제목
    genres = serializers.ListField(child=serializers.CharField())  # 장르 이름 리스트
    thumbnail_url = serializers.URLField(  # 최적화된(t_cover_big) 이미지 주소
        allow_null=True, required=False
    )
    rating = serializers.FloatField(allow_null=True)  # 10점 만점으로 환산된 평점

    # 참고: 만약 좋아요 수를 리스트에 포함하기로 결정했다면 아래 필드를 추가합니다.
    # like_count = serializers.IntegerField(default=0)
