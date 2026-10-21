"""
Serializadores DRF para validación y transformación de datos en la API de eventos.
"""

from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Max
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



def _labels(choices):
    """['Pendiente', 'En progreso', 'Hecho'] -> 'Pendiente, En progreso o Hecho'."""
    labels = [label for _, label in choices]
    return f"{', '.join(labels[:-1])} o {labels[-1]}"


_ALLOWED_STATUS = _labels(LogisticSubtask.Status.choices)

# Mensajes propios para los campos generados desde el modelo (sin textos genéricos de DRF)
DATE_ERRORS = {"invalid": "Ingresa una fecha válida.", "datetime": "Ingresa una fecha válida."}
HOURS_INVALID_MESSAGE = "Ingresa un número de horas válido, p. ej. 1.5."


def format_date(value):
    return f"{value.day:02d}/{MONTHS_SHORT[value.month - 1]}/{value.year}"


def calculate_progress_data(event):
    """Calcula el progreso de preparación del evento sin persistirlo (US-10, PI-152)."""
    # Se cuenta en Python para aprovechar prefetch_related("subtasks") en los listados
    subtasks = list(event.subtasks.all())
    total = len(subtasks)
    executed = sum(1 for t in subtasks if t.status == LogisticSubtask.Status.DONE)
    percentage = round((executed / total) * 100, 1) if total > 0 else 0.0
    return {
        "total": total,
        "executed": executed,
        "completed": executed,
        "percentage": percentage,
    }


class LogisticSubtaskSerializer(serializers.ModelSerializer):
    """
    Serializador para operaciones sobre subtareas logísticas.
    Al crear, la vista pasa el evento en el contexto (context={"event": evento}).
    """

    status = serializers.ChoiceField(
        choices=LogisticSubtask.Status.choices,
        required=False,
        error_messages={
            "invalid_choice": (
                f"El estado elegido no es válido. Elige {_ALLOWED_STATUS}."
            ),
        },
    )
    # Declarado aquí para que los mensajes propios ganen a los del MinValueValidator del modelo
    estimated_hours = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        required=False,
        error_messages={
            "invalid": HOURS_INVALID_MESSAGE,
            "null": "Las horas estimadas son obligatorias.",
            "max_decimal_places": "Usa como máximo 1 decimal, p. ej. 1.5.",
            "max_digits": HOURS_INVALID_MESSAGE,
            "max_whole_digits": HOURS_INVALID_MESSAGE,
            "max_string_length": HOURS_INVALID_MESSAGE,
        },
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

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
        extra_kwargs = {
            "name": {
                "error_messages": {
                    "required": "El nombre de la gestión es obligatorio.",
                    "blank": "El nombre de la gestión es obligatorio.",
                    "max_length": "El nombre de la gestión no puede superar los 200 caracteres.",
                }
            },
            "type": {"error_messages": {"invalid_choice": "Elige un tipo de gestión válido."}},
            "priority": {"error_messages": {"invalid_choice": "Elige una prioridad válida."}},
            "scheduled_date": {
                "error_messages": {
                    **DATE_ERRORS,
                    "required": "La fecha objetivo es obligatoria.",
                    "null": "La fecha objetivo es obligatoria.",
                }
            },
        }

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
        error_messages={"invalid": "No pudimos confirmar el cambio. Inténtalo de nuevo."},
    )
    resolution = serializers.ChoiceField(
        choices=[REDUCE_HOURS],
        required=False,
        error_messages={
            "invalid_choice": "La opción elegida para resolver el conflicto no es válida."
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


class EventProgressSerializer(serializers.Serializer):
    """Representación del progreso calculado de un evento (US-10, PI-151)."""

    event_id = serializers.IntegerField(read_only=True)
    event_name = serializers.CharField(read_only=True)
    total = serializers.IntegerField(read_only=True)
    executed = serializers.IntegerField(read_only=True)
    completed = serializers.IntegerField(read_only=True)
    percentage = serializers.FloatField(read_only=True)


class EventSerializer(serializers.ModelSerializer):
    """
    Serializador para eventos, con soporte para lectura de sus subtareas y progreso (PI-153).
    """

    subtasks = LogisticSubtaskSerializer(many=True, read_only=True)
    total_subtasks = serializers.IntegerField(source="subtasks.count", read_only=True)
    progress = serializers.SerializerMethodField()

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
            "event_time",
            "description",
            "status",
            "created_at",
            "total_subtasks",
            "progress",
            "subtasks",
        ]
        read_only_fields = ["id", "user", "created_at", "subtasks", "total_subtasks", "progress"]
        extra_kwargs = {
            "name": {
                "error_messages": {
                    "required": "El nombre del evento es obligatorio.",
                    "blank": "El nombre del evento no puede estar vacío.",
                    "max_length": "El nombre del evento no puede superar los 200 caracteres.",
                }
            },
            "event_type": {"error_messages": {"invalid_choice": "Elige un tipo de evento válido."}},
            "status": {"error_messages": {"invalid_choice": "Elige un estado de evento válido."}},
            "event_date": {
                "error_messages": {
                    **DATE_ERRORS,
                    "required": "La fecha del evento es obligatoria.",
                    "null": "La fecha del evento es obligatoria.",
                }
            },
            "event_time": {
                "error_messages": {
                    "invalid": "Ingresa una hora válida en formato HH:MM o HH:MM:SS.",
                }
            },
        }
        
    def get_progress(self, obj):
        return calculate_progress_data(obj)

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
        fecha que ya tenía el evento aunque haya pasado, pero no cambiarla por otra pasada
        ni dejarla antes de alguna de sus gestiones (que ya no se podrían reprogramar).
        """
        if self.instance is not None and value == self.instance.event_date:
            return value

        if value < timezone.localdate():
            raise serializers.ValidationError(
                "La fecha del evento no puede ser anterior a hoy."
            )

        if self.instance is not None:
            latest = self.instance.subtasks.aggregate(latest=Max("scheduled_date"))["latest"]
            if latest is not None and value < latest:
                raise serializers.ValidationError(
                    "La fecha del evento no puede quedar antes de sus gestiones: la última "
                    f"está programada para el {format_date(latest)}. Reprográmala primero."
                )
        return value


class TodaySubtaskSerializer(serializers.ModelSerializer):
    """Gestión en la vista 'Hoy', con el evento al que pertenece y su nota."""

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
            "note",
            "is_overdue",
        ]


def _event_filter_field():
    return serializers.IntegerField(
        required=False,
        min_value=1,
        error_messages={
            "invalid": "El evento seleccionado no es válido.",
            "min_value": "El evento seleccionado no es válido.",
        },
    )


# En Hoy no se muestran las gestiones hechas, así que no se puede filtrar por ese estado
TODAY_STATUS_CHOICES = [
    choice for choice in LogisticSubtask.Status.choices
    if choice[0] != LogisticSubtask.Status.DONE
]


class TodayFilterSerializer(serializers.Serializer):
    """Valida los parámetros de consulta opcionales de GET /api/today/ (US-05)."""

    event = _event_filter_field()
    status = serializers.ChoiceField(
        choices=LogisticSubtask.Status.choices,
        required=False,
        error_messages={
            "invalid_choice": (
                f"El estado elegido no es válido. Elige {_labels(TODAY_STATUS_CHOICES)}."
            ),
        },
    )

    def validate_status(self, value):
        if value == LogisticSubtask.Status.DONE:
            raise serializers.ValidationError(
                "Las gestiones hechas no aparecen en Hoy. Consulta su avance en Progreso."
            )
        return value


class ProgressFilterSerializer(serializers.Serializer):
    """Valida el parámetro opcional ?event= de GET /api/progress/ (US-10)."""

    event = _event_filter_field()


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