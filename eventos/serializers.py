"""
Serializadores DRF para validación y transformación de datos en la API de eventos.
"""

from decimal import Decimal
from rest_framework import serializers
from .models import Event, LogisticSubtask


class LogisticSubtaskSerializer(serializers.ModelSerializer):
    """
    Serializador para operaciones sobre subtareas logísticas.
    """

    class Meta:
        model = LogisticSubtask
        fields = [
            "id",
            "event",
            "name",
            "type",
            "scheduled_date",
            "estimated_hours",
            "priority",
            "status",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_estimated_hours(self, value):
        """
        Garantiza que las horas estimadas sean numéricas y estrictamente mayores a cero (PI-28).
        """
        if value is None or value <= Decimal("0"):
            raise serializers.ValidationError("Las horas estimadas deben ser un valor mayor a 0.")
        return value


class EventSerializer(serializers.ModelSerializer):
    """
    Serializador para eventos, con soporte para lectura de sus subtareas asociadas.
    """
    subtasks = LogisticSubtaskSerializer(many=True, read_only=True)
    total_subtasks = serializers.IntegerField(source="subtasks.count", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "user",
            "name",
            "event_type",
            "contact",
            "location",
            "event_date",
            "description",
            "status",
            "created_at",
            "total_subtasks",
            "subtasks",
        ]
        read_only_fields = ["id", "user", "created_at", "subtasks", "total_subtasks"]

    def validate_name(self, value):
        """Valida que el nombre no contenga únicamente espacios en blanco."""
        if not value.strip():
            raise serializers.ValidationError("El nombre del evento no puede estar vacío.")
        return value.strip()