"""
Serializadores DRF para validación y transformación de datos en la API de eventos.
"""

from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    DAILY_LIMIT_MAX,
    DAILY_LIMIT_MIN,
    Event,
    LogisticSubtask,
    User,
)
from .workload import format_hours

# Formato único de fechas que ve el usuario (igual que en el frontend): DD/Mmm/AAAA, p. ej. 11/Sep/2026
MONTHS_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def format_date(value):
    return f"{value.day:02d}/{MONTHS_SHORT[value.month - 1]}/{value.year}"


class LogisticSubtaskSerializer(serializers.ModelSerializer):
    """
    Serializador para operaciones sobre subtareas logísticas.
    Al crear, la vista pasa el evento en el contexto (context={"event": evento}).
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

    def validate_scheduled_date(self, value):
        """
        La fecha objetivo debe estar entre hoy y la fecha del evento. Al editar se
        permite conservar la fecha que ya tenía la gestión (p. ej. una vencida a la
        que solo se le cambia el estado), pero no moverla fuera de ese rango.
        """
        if self.instance is not None and value == self.instance.scheduled_date:
            return value

        if value < timezone.localdate():
            raise serializers.ValidationError(
                "La fecha objetivo no puede ser anterior a hoy."
            )

        event = self.instance.event if self.instance is not None else self.context.get("event")
        if event is not None and value > event.event_date:
            raise serializers.ValidationError(
                "La fecha objetivo no puede ser posterior a la fecha del evento "
                f"({format_date(event.event_date)})."
            )
        return value

    def validate(self, attrs):
        """
        Al resolver un conflicto reduciendo horas (US-08), las nuevas horas deben
        ser mayores que cero y menores que las que la gestión tenía estimadas.
        """
        if self.context.get("resolution") != SubtaskUpdateOptionsSerializer.REDUCE_HOURS:
            return attrs

        hours = attrs.get("estimated_hours")
        if hours is None:
            raise serializers.ValidationError(
                {"estimated_hours": ["Indica las nuevas horas estimadas de la gestión."]}
            )
        current = self.instance.estimated_hours
        if hours >= current:
            raise serializers.ValidationError(
                {
                    "estimated_hours": [
                        "Las horas reducidas deben ser mayores que 0 y menores que "
                        f"las estimadas actualmente ({format_hours(current)}h)."
                    ]
                }
            )
        return attrs


class SubtaskUpdateOptionsSerializer(serializers.Serializer):
    """
    Campos de control opcionales de PATCH /api/subtasks/:id/ (US-07, US-08).
    No se guardan en la gestión; indican cómo tratar el conflicto de sobrecarga.
    """

    REDUCE_HOURS = "reduce_hours"

    confirm_overload = serializers.BooleanField(
        required=False,
        default=False,
        error_messages={"invalid": "El campo 'confirm_overload' debe ser verdadero o falso."},
    )
    resolution = serializers.ChoiceField(
        choices=[REDUCE_HOURS],
        required=False,
        error_messages={
            "invalid_choice": f"La resolución '{{input}}' no es válida. Valor permitido: {REDUCE_HOURS}."
        },
    )


class DailyLimitSerializer(serializers.ModelSerializer):
    """Límite diario de horas de gestión del organizador (US-12)."""

    _RANGE_MESSAGE = (
        f"El límite diario debe ser un número entero de horas entre "
        f"{DAILY_LIMIT_MIN} y {DAILY_LIMIT_MAX}."
    )

    daily_hours_limit = serializers.IntegerField(
        min_value=DAILY_LIMIT_MIN,
        max_value=DAILY_LIMIT_MAX,
        error_messages={
            "required": "El límite diario es obligatorio.",
            "null": "El límite diario es obligatorio.",
            "invalid": _RANGE_MESSAGE,
            "min_value": _RANGE_MESSAGE,
            "max_value": _RANGE_MESSAGE,
            "max_string_length": _RANGE_MESSAGE,
        },
    )

    class Meta:
        model = User
        fields = ["daily_hours_limit"]


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

    def validate_event_date(self, value):
        """
        No se pueden crear eventos en el pasado. Al editar, se permite conservar la
        fecha que ya tenía el evento aunque haya pasado, pero no cambiarla por otra pasada.
        """
        unchanged = self.instance is not None and value == self.instance.event_date
        if value < timezone.localdate() and not unchanged:
            raise serializers.ValidationError(
                "La fecha del evento no puede ser anterior a hoy."
            )
        return value


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


class RegisterSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/register/ (US-11)."""

    first_name = serializers.CharField(
        max_length=150,
        error_messages={
            "required": "El nombre es obligatorio.",
            "blank": "El nombre es obligatorio.",
            "max_length": "El nombre no puede superar los 150 caracteres.",
        },
    )
    last_name = serializers.CharField(
        max_length=150,
        error_messages={
            "required": "El apellido es obligatorio.",
            "blank": "El apellido es obligatorio.",
            "max_length": "El apellido no puede superar los 150 caracteres.",
        },
    )
    email = serializers.EmailField(
        max_length=150,
        error_messages={
            "required": "El correo es obligatorio.",
            "blank": "El correo es obligatorio.",
            "invalid": "Ingresa un correo válido.",
            "max_length": "El correo no puede superar los 150 caracteres.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        error_messages={
            "required": "La contraseña es obligatoria.",
            "blank": "La contraseña es obligatoria.",
        },
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return email

    def validate(self, attrs):
        # Las reglas de AUTH_PASSWORD_VALIDATORS (longitud, contraseñas comunes, etc.)
        candidate = User(
            username=attrs["email"],
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        # El correo es el identificador de inicio de sesión; se usa también como username
        return User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"].strip(),
            last_name=validated_data["last_name"].strip(),
        )
