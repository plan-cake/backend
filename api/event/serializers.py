from rest_framework import serializers

from api.utils import TimeZoneField


# Defining an object-oriented inheritance structure of serializers for DRY
class CustomCodeSerializer(serializers.Serializer):
    custom_code = serializers.CharField(required=False, max_length=255)


class EventCodeSerializer(serializers.Serializer):
    event_code = serializers.CharField(required=True, max_length=255)


class EventInfoSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=50)
    duration = serializers.IntegerField(required=False)
    timeslots = serializers.ListField(
        child=serializers.DateTimeField(), required=True, allow_empty=False
    )
    time_zone = TimeZoneField(required=True)

    def validate(self, attrs):
        DURATION_VALUES = [15, 30, 45, 60]
        if "duration" in attrs and attrs.get("duration") not in DURATION_VALUES:
            raise serializers.ValidationError(
                {
                    "duration": [
                        f"Invalid value. Valid values are: {', '.join(map(str, DURATION_VALUES))}"
                    ]
                }
            )
        return super().validate(attrs)


class DateEventCreateSerializer(EventInfoSerializer, CustomCodeSerializer):
    pass


class WeekEventCreateSerializer(EventInfoSerializer, CustomCodeSerializer):
    pass


class DateEventEditSerializer(EventInfoSerializer, EventCodeSerializer):
    pass


class WeekEventEditSerializer(EventInfoSerializer, EventCodeSerializer):
    pass


class EventDetailSerializer(EventInfoSerializer):
    is_creator = serializers.BooleanField(required=True)
    event_type = serializers.ChoiceField(required=True, choices=["Date", "Week"])
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=True)
