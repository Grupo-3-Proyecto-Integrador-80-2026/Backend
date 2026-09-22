"""
Configuración de rutas de la API de eventos.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Monitoreo y diagnóstico
    path("health/", views.health_check, name="health-check"),
    path("db-test/", views.db_test, name="db-test"),

    # US-01 & US-03: Eventos
    path("events/", views.EventListCreateAPIView.as_view(), name="event-list-create"),
    path("events/<int:event_id>/", views.EventDetailAPIView.as_view(), name="event-detail"),

    # US-02: Subtareas por Evento
    path("events/<int:event_id>/subtasks/", views.EventSubtaskListCreateAPIView.as_view(), name="event-subtask-list-create"),

    # US-03: Gestión individual de Subtareas
    path("subtasks/<int:subtask_id>/", views.SubtaskDetailAPIView.as_view(), name="subtask-detail"),
]