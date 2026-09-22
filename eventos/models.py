"""
Modelos de datos del backend — Mini-proyecto 1: Organizador de Eventos Independientes.
Proyecto Integrador I (750018C).

Define las entidades centrales:
- User: Organizador de eventos con límite diario de horas.
- Event: Evento independiente a gestionar.
- LogisticSubtask: Tareas logísticas asociadas a un evento.
"""

from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator


class User(AbstractUser):
    """
    Usuario del sistema (organizador de eventos).
    Extiende AbstractUser para preservar la seguridad y autenticación nativa de Django.
    """
    daily_hours_limit = models.PositiveIntegerField(
        default=6,
        help_text="Límite de horas diarias que el usuario puede dedicar a gestiones logísticas."
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.username


class Event(models.Model):
    """
    Evento independiente organizado por un usuario.
    Agrupa el plan de trabajo logístico inicial y su seguimiento.
    """

    class EventType(models.TextChoices):
        """Tipos de eventos sugeridos por el alcance funcional."""
        WEDDING = "wedding", "Boda"
        SOCIAL = "social", "Social"
        CORPORATE = "corporate", "Corporativo"
        BIRTHDAY = "birthday", "Cumpleaños"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        """Estado general del ciclo de vida del evento."""
        PLANNING = "planning", "Planeando"
        IN_PROGRESS = "in_progress", "En curso"
        FINISHED = "finished", "Finalizado"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="Usuario propietario del evento."
    )
    name = models.CharField(max_length=200, help_text="Nombre del evento.")
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        default=EventType.OTHER,
        help_text="Tipo o categoría del evento."
    )
    contact = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Nombre o datos de contacto del cliente."
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Lugar físico o plazo límite general del evento."
    )
    event_date = models.DateField(
        help_text="Fecha en la que se llevará a cabo el evento."
    )
    description = models.TextField(blank=True, null=True, help_text="Descripción o notas del evento.")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNING,
        help_text="Estado actual del evento."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ["-event_date"]

    def __str__(self):
        return f"{self.name} ({self.get_event_type_display()})"


class LogisticSubtask(models.Model):
    """
    Gestión logística específica dentro de un evento (T1, T2, T3, T4).
    """

    class TaskType(models.TextChoices):
        """Tipos mínimos requeridos para clasificación logística."""
        BOOK_VENUE = "book_venue", "Reservar salón"
        SEND_INVITATIONS = "send_invitations", "Enviar invitaciones"
        CONFIRM_CATERING = "confirm_catering", "Confirmar catering"
        COORDINATE_VENDORS = "coordinate_vendors", "Coordinar proveedores"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En progreso"
        DONE = "done", "Hecho"
        POSTPONED = "postponed", "Pospuesto"

    class Priority(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="subtasks",
        help_text="Evento al que pertenece esta gestión."
    )
    name = models.CharField(max_length=200, help_text="Nombre de la gestión logística.")
    type = models.CharField(
        max_length=50,
        choices=TaskType.choices,
        default=TaskType.OTHER,
        help_text="Tipo de gestión logística."
    )
    scheduled_date = models.DateField(
        help_text="Fecha objetivo o plazo planificado para ejecutar la gestión."
    )
    estimated_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("1.0"),
        validators=[MinValueValidator(Decimal("0.1"))],
        help_text="Horas estimadas de trabajo (mayor a 0, entero o decimal simple)."
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        help_text="Nivel de prioridad de la gestión."
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Estado de ejecución de la gestión."
    )
    note = models.TextField(
        blank=True,
        null=True,
        help_text="Nota de avance o motivo de postergación."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subtarea logística"
        verbose_name_plural = "Subtareas logísticas"
        ordering = ["scheduled_date"]

    def __str__(self):
        return f"{self.name} - {self.event.name}"