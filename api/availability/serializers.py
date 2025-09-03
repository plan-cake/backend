from rest_framework import serializers

from api.utils import TimeZoneField


class EventCodeSerializer(serializers.Serializer):
    event_code = serializers.CharField(required=True, max_length=255)


class DisplayNameSerializer(serializers.Serializer):
    display_name = serializers.CharField(required=True, max_length=25)


class DisplayNameCheckSerializer(EventCodeSerializer, DisplayNameSerializer):
    pass


class AvailabilitySerializer(serializers.Serializer):
    availability = serializers.ListField(
        child=serializers.ListField(
            child=serializers.BooleanField(), required=True, min_length=4
        ),
        required=True,
        min_length=1,
    )


class AvailabilityAddSerializer(
    EventCodeSerializer, DisplayNameSerializer, AvailabilitySerializer
):
    time_zone = TimeZoneField(required=True)


class AvailableDatesSerializer(serializers.Serializer):
    available_dates = serializers.ListField(
        child=serializers.DateTimeField(required=True), required=True
    )


class EventAvailabilitySerializer(serializers.Serializer):
    participants = serializers.ListField(
        child=serializers.CharField(required=True, max_length=25),
        required=True,
    )
    availability = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(
                child=serializers.CharField(required=True, max_length=25),
                required=True,
            ),
            required=True,
            min_length=4,
        ),
        required=True,
        min_length=1,
    )
