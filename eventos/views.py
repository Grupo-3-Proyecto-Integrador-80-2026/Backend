"""
Vistas y controladores API REST para el Mini-proyecto 1.
Implementa endpoints para eventos y subtareas logísticas cumpliendo con US-01, US-02 y US-03.
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import JsonResponse

from .models import User, Event, LogisticSubtask
from .serializers import EventSerializer, LogisticSubtaskSerializer
from .utils import resolve_request_user


def health_check(request):
    """Verifica la disponibilidad básica del servicio."""
    return JsonResponse({"status": "ok"})


def db_test(request):
    """Verifica conectividad con la base de datos."""
    user = User.objects.first()
    if user:
        return JsonResponse({"message": f"Conexión exitosa. Usuario encontrado: {user.username}"})
    return JsonResponse({"message": "Conectado a la BD, pero no existen usuarios registrados aún."})


class EventListCreateAPIView(APIView):
    """
    Endpoint para listar eventos del usuario actual y crear nuevos eventos (US-01 / PI-14).
    Ruta: /api/events/
    """

    def get(self, request):
        """Lista todos los eventos pertenecientes al usuario actual."""
        user = resolve_request_user(request)
        events = Event.objects.filter(user=user).prefetch_related("subtasks")
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Crea un nuevo evento asociado al usuario actual (demo en Sprint 1 o autenticado en Sprint 2).
        """
        user = resolve_request_user(request)
        serializer = EventSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {"error": "Datos inválidos para la creación del evento.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class EventDetailAPIView(APIView):
    """
    Endpoint para obtener, actualizar parcialmente y eliminar un evento (US-03 / PI-38, PI-39).
    Ruta: /api/events/<int:event_id>/
    """

    def _get_event(self, request, event_id):
        """
        Obtiene el evento validando que exista y pertenezca al usuario (PI-29, PI-39).
        """
        user = resolve_request_user(request)
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    def get(self, request, event_id):
        """Retorna el detalle del evento con sus subtareas asociadas."""
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no existe o no tiene permisos para consultarlo."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, event_id):
        """Actualización parcial de atributos del evento."""
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no fue encontrado para actualizar."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(
            {"error": "Error de validación al actualizar el evento.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, event_id):
        """Elimina un evento y sus subtareas en cascada."""
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no fue encontrado para eliminar."},
                status=status.HTTP_404_NOT_FOUND
            )

        event.delete()
        return Response(
            {"message": f"Evento '{event.name}' eliminado exitosamente."},
            status=status.HTTP_200_OK
        )


class EventSubtaskListCreateAPIView(APIView):
    """
    Endpoint para listar y crear subtareas logísticas dentro de un evento (US-02 / PI-27, PI-29).
    Ruta: /api/events/<int:event_id>/subtasks/
    """

    def _get_event(self, request, event_id):
        user = resolve_request_user(request)
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    def get(self, request, event_id):
        """Retorna todas las subtareas asociadas a un evento."""
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no existe o no pertenece al usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        subtasks = event.subtasks.all()
        serializer = LogisticSubtaskSerializer(subtasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, event_id):
        """Crea una nueva subtarea logística ligada al evento referenciado."""
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"No se puede crear la subtarea: el evento con ID {event_id} no existe o no pertenece al usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LogisticSubtaskSerializer(data=request.data)
        if serializer.is_valid():
            # Pasamos el evento verificado directamente al guardar
            serializer.save(event=event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {"error": "Datos inválidos para la subtarea logística.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class SubtaskDetailAPIView(APIView):
    """
    Endpoint para consultar, actualizar (PATCH) y eliminar (DELETE) una subtarea individual (US-03 / PI-38, PI-39).
    Ruta: /api/subtasks/<int:subtask_id>/
    """

    def _get_subtask(self, request, subtask_id):
        user = resolve_request_user(request)
        try:
            return LogisticSubtask.objects.get(id=subtask_id, event__user=user)
        except LogisticSubtask.DoesNotExist:
            return None

    def get(self, request, subtask_id):
        """Consulta el estado y datos de una subtarea puntual."""
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {"error": f"La subtarea logística con ID {subtask_id} no fue encontrada."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LogisticSubtaskSerializer(subtask)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, subtask_id):
        """Actualiza parcialmente una subtarea (reprogramación, estado, horas, notas)."""
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {"error": f"La subtarea con ID {subtask_id} no existe o no tiene permisos para modificarla."},
                status=status.HTTP_404_NOT_FOUND
            )

        payload = request.data.copy()
        payload.pop("event", None)

        serializer = LogisticSubtaskSerializer(subtask, data=payload, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(
            {"error": "Error de validación al actualizar la subtarea.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, subtask_id):
        """Elimina la subtarea logística especificada."""
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {"error": f"La subtarea con ID {subtask_id} no fue encontrada para eliminar."},
                status=status.HTTP_404_NOT_FOUND
            )

        subtask.delete()
        return Response(
            {"message": f"Subtarea '{subtask.name}' eliminada correctamente."},
            status=status.HTTP_200_OK
        )