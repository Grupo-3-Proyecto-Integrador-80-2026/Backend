"""
Serializadores DRF para validación y transformación de datos en la API de eventos.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import Event, LogisticSubtask, User


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
        read_only_fields = ["id", "event", "created_at", "updated_at"]

    def validate_estimated_hours(self, value):
        """
        Garantiza que las horas estimadas sean numéricas y estrictamente mayores a cero (PI-28).
        """
        if value is None or value <= Decimal("0"):
            raise serializers.ValidationError(
                "Las horas estimadas deben ser un valor mayor a 0."
            )
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
            raise serializers.ValidationError(
                "El nombre del evento no puede estar vacío."
            )
        return value.strip()


class TodaySubtaskSerializer(serializers.ModelSerializer):
    """Gestión en la vista 'Hoy', con el evento al que pertenece."""

    event_id = serializers.IntegerField(source="event.id", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = LogisticSubtask
        fields = [
            "id",
            "name",
            "type",
            "event_id",
            "event_name",
            "scheduled_date",
            "estimated_hours",
            "priority",
            "status",
            "is_overdue",
        ]


_ALLOWED_STATUS = ", ".join(LogisticSubtask.Status.values)


class TodayFilterSerializer(serializers.Serializer):
    """Valida los parámetros de consulta opcionales de GET /api/today/ (US-05)."""

    event = serializers.IntegerField(
        required=False,
        min_value=1,
        error_messages={
            "invalid": "El filtro 'event' debe ser un número entero.",
            "min_value": "El filtro 'event' debe ser un ID válido (mayor a 0).",
        },
    )
    status = serializers.ChoiceField(
        choices=LogisticSubtask.Status.choices,
        required=False,
        error_messages={
            "invalid_choice": (
                f"El estado '{{input}}' no es válido. "
                f"Valores permitidos: {_ALLOWED_STATUS}."
            ),
        },
    )


class LoginSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/login/ (US-11, PI-166)."""

    email = serializers.EmailField(
        error_messages={
            "required": "El correo es obligatorio.",
            "blank": "El correo es obligatorio.",
            "invalid": "Ingresa un correo válido.",
        }
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        error_messages={
            "required": "La contraseña es obligatoria.",
            "blank": "La contraseña es obligatoria.",
        },
    )


class AuthUserSerializer(serializers.ModelSerializer):
    """Datos públicos del organizador autenticado (nunca incluye la contraseña)."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "daily_hours_limit",
        ]
        read_only_fields = fields
