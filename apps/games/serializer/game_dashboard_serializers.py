from rest_framework import serializers


class GameDashboardSerializer(serializers.Serializer):
    basic_info = serializers.DictField()
    performance_metrics = serializers.DictField()
    user_reaction_analysis = serializers.DictField()
    blacklist_impact = serializers.DictField()
