"""
Modelos de datos del backend — Mini-proyecto 1: Organizador de Eventos
Independientes (Proyecto Integrador I, 750018C).

Estas tres entidades (User, Event, LogisticSubtask) cubren el modelo
relacional completo del MVP: un usuario organiza varios eventos, y cada
evento tiene su propio plan de trabajo logístico compuesto por subtareas.
"""

from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Usuario del sistema (organizador de eventos).

    Extiende AbstractUser en lugar de crear un modelo desde cero para
    reutilizar la infraestructura de autenticación ya probada de Django:
    hasheo de contraseñas (nunca se guardan en texto plano), verificación
    de login, permisos y sesión. Los campos heredados incluyen username,
    email, first_name, last_name, password, is_active, is_staff y
    date_joined, entre otros.

    Único campo propio del dominio: el límite diario de horas que el
    usuario puede dedicarle a la gestión de sus eventos.
    """

    daily_hours_limit = models.PositiveIntegerField(
        default=6,
        help_text=(
            "Límite de horas diarias que el usuario puede dedicar a "
            "gestiones logísticas. Se usa para detectar el conflicto de "
            "sobrecarga al reprogramar subtareas (T3)."
        ),
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.username


class Event(models.Model):
    """
    Evento independiente organizado por un usuario (ej. una boda, un
    lanzamiento, un cumpleaños). Agrupa el plan de trabajo logístico
    (subtareas) necesario para su preparación.
    """

    class Status(models.TextChoices):
        """Estado general del evento en su ciclo de vida."""
        PLANNING = "planning", "Planeando"
        IN_PROGRESS = "in_progress", "En curso"
        FINISHED = "finished", "Finalizado"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="Usuario dueño del evento. Al eliminar el usuario, se eliminan sus eventos.",
    )
    name = models.CharField(max_length=200, help_text="Nombre del evento.")
    event_date = models.DateField(
        help_text="Fecha en la que ocurre el evento (distinta de las fechas de sus subtareas)."
    )
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ["-event_date"]

    def __str__(self):
        return self.name


class LogisticSubtask(models.Model):
    """
    Gestión logística puntual dentro del plan de trabajo de un evento
    (ej. reservar salón, confirmar catering, coordinar proveedores).

    Es la entidad central del MVP: soporta directamente las cuatro
    tareas núcleo (T1-T4) exigidas por el enunciado del curso.

    Trazabilidad T1-T4:
        T1 (Plan inicial):   se crea con `scheduled_date` y `estimated_hours`.
        T2 (Vista "Hoy"):    se filtra por scheduled_date <= hoy AND status != done.
        T3 (Reprogramar):    se actualiza `scheduled_date`. El conflicto de
                             sobrecarga se calcula sumando `estimated_hours`
                             de todas las subtareas del usuario programadas
                             para el mismo día, y comparando ese total
                             contra `User.daily_hours_limit`.
        T4 (Progreso):       se actualiza `status` (done/postponed) y `note`.
                             El % de progreso de un evento se calcula
                             contando sus subtareas en status=done.
    """

    class TaskType(models.TextChoices):
        """Tipo de gestión logística, según los ejemplos del enunciado."""
        BOOK_VENUE = "book_venue", "Reservar salón"
        SEND_INVITATIONS = "send_invitations", "Enviar invitaciones"
        CONFIRM_CATERING = "confirm_catering", "Confirmar catering"
        COORDINATE_VENDORS = "coordinate_vendors", "Coordinar proveedores"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        """
        Estado de ejecución de la subtarea. `DONE` y `POSTPONED` son los
        valores que se registran al reportar el avance real (T4).
        """
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En progreso"
        DONE = "done", "Hecho"
        POSTPONED = "postponed", "Pospuesto"

    class Priority(models.TextChoices):
        """Prioridad informativa de la subtarea (no interviene en el cálculo de conflicto)."""
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="subtasks",
        help_text="Evento al que pertenece esta gestión logística.",
    )
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=50, choices=TaskType.choices, default=TaskType.OTHER)
    scheduled_date = models.DateField(
        help_text=(
            "Fecha programada para ejecutar la gestión; funciona como el "
            "'plazo' de T1 y es el campo que se actualiza al reprogramar (T3)."
        )
    )
    estimated_hours = models.PositiveIntegerField(
        default=1,
        help_text="Horas estimadas para completar la gestión. Se usa en el cálculo de conflicto (T3).",
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(
        blank=True,
        null=True,
        help_text="Comentario opcional sobre el avance (ej. por qué se pospuso).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Se actualiza automáticamente en cada cambio; sirve como rastro básico de auditoría.",
    )

    class Meta:
        verbose_name = "Subtarea logística"
        verbose_name_plural = "Subtareas logísticas"
        ordering = ["scheduled_date"]

    def __str__(self):
        return self.name