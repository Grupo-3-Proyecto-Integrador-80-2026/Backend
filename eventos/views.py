"""
Vistas y controladores API REST para el Mini-proyecto 1.
Implementa endpoints para eventos y subtareas logísticas cumpliendo con US-01, US-02 y US-03.
Documentado con Swagger / OpenAPI mediante drf-spectacular.
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema

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
    """Gestión de listado y creación de eventos."""

    @extend_schema(
        summary="Listar eventos",
        description="Obtiene todos los eventos asociados al usuario actual.",
        responses={200: EventSerializer(many=True)}
    )
    def get(self, request):
        user = resolve_request_user(request)
        events = Event.objects.filter(user=user).prefetch_related("subtasks")
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear un evento",
        description="Crea un nuevo evento asociado al usuario actual.",
        request=EventSerializer,
        responses={201: EventSerializer, 400: dict}
    )
    def post(self, request):
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
    """Gestión individual de un evento (detalle, actualización, eliminación)."""

    def _get_event(self, request, event_id):
        user = resolve_request_user(request)
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    @extend_schema(
        summary="Obtener detalle de un evento",
        description="Retorna el evento especificado con su lista de subtareas.",
        responses={200: EventSerializer, 404: dict}
    )
    def get(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no existe o no tiene permisos para consultarlo."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar parcialmente un evento",
        description="Modifica campos específicos de un evento.",
        request=EventSerializer,
        responses={200: EventSerializer, 400: dict, 404: dict}
    )
    def patch(self, request, event_id):
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

    @extend_schema(
        summary="Eliminar un evento",
        description="Elimina el evento y todas sus subtareas en cascada.",
        responses={200: dict, 404: dict}
    )
    def delete(self, request, event_id):
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
    """Gestión de subtareas logísticas asociadas a un evento."""

    def _get_event(self, request, event_id):
        user = resolve_request_user(request)
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    @extend_schema(
        summary="Listar subtareas de un evento",
        description="Obtiene todas las gestiones logísticas pertenecientes a un evento.",
        responses={200: LogisticSubtaskSerializer(many=True), 404: dict}
    )
    def get(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"El evento con ID {event_id} no existe o no pertenece al usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        subtasks = event.subtasks.all()
        serializer = LogisticSubtaskSerializer(subtasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear una subtarea en un evento",
        description="Crea una gestión logística dentro del evento indicado.",
        request=LogisticSubtaskSerializer,
        responses={201: LogisticSubtaskSerializer, 400: dict, 404: dict}
    )
    def post(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {"error": f"No se puede crear la subtarea: el evento con ID {event_id} no existe o no pertenece al usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LogisticSubtaskSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(event=event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {"error": "Datos inválidos para la subtarea logística.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class SubtaskDetailAPIView(APIView):
    """Gestión individual de una subtarea (consultar, modificar o eliminar)."""

    def _get_subtask(self, request, subtask_id):
        user = resolve_request_user(request)
        try:
            return LogisticSubtask.objects.get(id=subtask_id, event__user=user)
        except LogisticSubtask.DoesNotExist:
            return None

    @extend_schema(
        summary="Obtener detalle de una subtarea",
        description="Consulta los datos de una subtarea logística específica.",
        responses={200: LogisticSubtaskSerializer, 404: dict}
    )
    def get(self, request, subtask_id):
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {"error": f"La subtarea logística con ID {subtask_id} no fue encontrada."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LogisticSubtaskSerializer(subtask)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar parcialmente una subtarea",
        description="Permite reprogramar fechas, actualizar estado (hecho/pospuesto), horas estimadas o notas.",
        request=LogisticSubtaskSerializer,
        responses={200: LogisticSubtaskSerializer, 400: dict, 404: dict}
    )
    def patch(self, request, subtask_id):
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

    @extend_schema(
        summary="Eliminar una subtarea",
        description="Elimina la gestión logística especificada.",
        responses={200: dict, 404: dict}
    )
    def delete(self, request, subtask_id):
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