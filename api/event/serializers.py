from rest_framework import serializers


# Defining an object-oriented inheritance structure of serializers for DRY
class CustomCodeSerializer(serializers.Serializer):
    custom_code = serializers.CharField(required=False, max_length=255)


class EventCodeSerializer(serializers.Serializer):
    event_code = serializers.CharField(required=True, max_length=255)


class EventInfoSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.ChoiceField(required=False, choices=["15", "30", "45", "60"])
    start_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    end_hour = serializers.IntegerField(required=True, min_value=0, max_value=24)
    time_zone = serializers.CharField(required=True, max_length=64)


class DateEventInfoSerializer(EventInfoSerializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)


class WeekEventInfoSerializer(EventInfoSerializer):
    start_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)
    end_weekday = serializers.IntegerField(required=True, min_value=0, max_value=6)


class DateEventCreateSerializer(DateEventInfoSerializer, CustomCodeSerializer):
    pass


class WeekEventCreateSerializer(WeekEventInfoSerializer, CustomCodeSerializer):
    pass


class DateEventEditSerializer(DateEventInfoSerializer, EventCodeSerializer):
    pass


class WeekEventEditSerializer(WeekEventInfoSerializer, EventCodeSerializer):
    pass
