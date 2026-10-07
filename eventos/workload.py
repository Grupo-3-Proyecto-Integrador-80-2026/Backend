"""
Carga diaria de gestión y conflicto por sobrecarga (US-07, US-08, US-12).

La carga de un día es la suma de las horas estimadas de las gestiones activas
(pendientes o en progreso) del organizador con esa fecha objetivo. Hay conflicto
solo cuando la carga resultante SUPERA el límite diario; igualarlo está permitido.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import LogisticSubtask

# Las gestiones hechas o pospuestas no ocupan horas del día.
ACTIVE_STATUSES = (LogisticSubtask.Status.PENDING, LogisticSubtask.Status.IN_PROGRESS)

MAX_SUGGESTED_DATES = 3


def format_hours(value):
    """7.0 -> '7', 6.5 -> '6.5'."""
    value = Decimal(value).normalize()
    return f"{value:f}"


def daily_load(user, day, exclude_id=None):
    """Horas de gestión activas que el organizador ya tiene planificadas en `day`."""
    subtasks = LogisticSubtask.objects.filter(
        event__user=user, scheduled_date=day, status__in=ACTIVE_STATUSES
    )
    if exclude_id is not None:
        subtasks = subtasks.exclude(id=exclude_id)
    return subtasks.aggregate(total=Sum("estimated_hours"))["total"] or Decimal("0")


def suggest_dates(user, subtask, hours, avoid):
    """
    Días entre hoy y la fecha del evento en los que la gestión cabe sin superar
    el límite, empezando por los más cercanos a la fecha que se quería (`avoid`).
    """
    limit = user.daily_hours_limit
    start = timezone.localdate()
    end = subtask.event.event_date
    if end < start:
        return []

    candidates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    candidates = [d for d in candidates if d != avoid]
    # Más cercano primero; ante igual distancia, el día posterior (retrasar) primero.
    candidates.sort(key=lambda d: (abs((d - avoid).days), d < avoid))

    suggestions = []
    for day in candidates:
        if daily_load(user, day, exclude_id=subtask.id) + hours <= limit:
            suggestions.append(day)
            if len(suggestions) == MAX_SUGGESTED_DATES:
                break
    return sorted(suggestions)


def detect_overload(user, subtask, day, hours):
    """
    Devuelve el detalle del conflicto si dejar la gestión en `day` con `hours`
    horas supera el límite diario del organizador; si no hay conflicto, None.
    """
    planned = daily_load(user, day, exclude_id=subtask.id)
    resulting = planned + hours
    limit = user.daily_hours_limit
    if resulting <= limit:
        return None

    return {
        "conflict": "daily_overload",
        "date": day.isoformat(),
        "planned_hours": float(planned),
        "subtask_hours": float(hours),
        "resulting_hours": float(resulting),
        "limit_hours": limit,
        "excess_hours": float(resulting - limit),
        "message": (
            f"Quedarías con {format_hours(resulting)}h de gestión planificadas "
            f"(límite {limit}h)."
        ),
        "suggested_dates": [d.isoformat() for d in suggest_dates(user, subtask, hours, day)],
        "options": [
            {"action": "move", "label": "Mover la gestión a otro día"},
            {"action": "reduce_hours", "label": "Reducir las horas estimadas"},
            {"action": "postpone", "label": "Posponer la gestión"},
        ],
    }
