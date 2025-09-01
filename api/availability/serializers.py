from rest_framework import serializers

from api.utils import TimeZoneField


class EventCodeSerializer(serializers.Serializer):
    event_code = serializers.CharField(required=True, max_length=255)


class DisplayNameSerializer(serializers.Serializer):
    display_name = serializers.CharField(required=True, max_length=25)


class DisplayNameCheckSerializer(EventCodeSerializer, DisplayNameSerializer):
    pass


class DateAvailabilityAddSerializer(EventCodeSerializer, DisplayNameSerializer):
    availability = serializers.ListField(
        child=serializers.ListField(
            child=serializers.BooleanField(), required=True, min_length=4
        ),
        required=True,
        min_length=1,
    )
    time_zone = TimeZoneField(required=True)
