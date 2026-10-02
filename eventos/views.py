"""
Vistas y controladores API REST para el Mini-proyecto 1.
Implementa endpoints para eventos y subtareas logísticas cumpliendo con US-01, US-02 y US-03.
Documentado con Swagger / OpenAPI mediante drf-spectacular.
"""

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UPCOMING_WINDOW_DAYS, Event, LogisticSubtask, User
from .serializers import (
    AuthUserSerializer,
    EventSerializer,
    LoginSerializer,
    LogisticSubtaskSerializer,
    RegisterSerializer,
    TodayFilterSerializer,
    TodaySubtaskSerializer,
)

def health_check(request):
    """Verifica la disponibilidad básica del servicio."""
    return JsonResponse({"status": "ok"})


def db_test(request):
    """Verifica conectividad con la base de datos (sin exponer datos de usuarios)."""
    try:
        User.objects.exists()
    except Exception:
        return JsonResponse(
            {"message": "No se pudo conectar con la base de datos."}, status=503
        )
    return JsonResponse({"message": "Conexión exitosa con la base de datos."})


class EventListCreateAPIView(APIView):
    """Gestión de listado y creación de eventos."""

    @extend_schema(
        summary="Listar eventos",
        description="Obtiene todos los eventos asociados al usuario actual.",
        responses={200: EventSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        events = Event.objects.filter(user=user).prefetch_related("subtasks")
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear un evento",
        description="Crea un nuevo evento asociado al usuario actual.",
        request=EventSerializer,
        responses={201: EventSerializer, 400: dict},
    )
    def post(self, request):
        user = request.user
        serializer = EventSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {
                "error": "Datos inválidos para la creación del evento.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class EventDetailAPIView(APIView):
    """Gestión individual de un evento (detalle, actualización, eliminación)."""

    def _get_event(self, request, event_id):
        user = request.user
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    @extend_schema(
        summary="Obtener detalle de un evento",
        description="Retorna el evento especificado con su lista de subtareas.",
        responses={200: EventSerializer, 404: dict},
    )
    def get(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {
                    "error": f"El evento con ID {event_id} no existe o no tiene permisos para consultarlo."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = EventSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar parcialmente un evento",
        description="Modifica campos específicos de un evento.",
        request=EventSerializer,
        responses={200: EventSerializer, 400: dict, 404: dict},
    )
    def patch(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {
                    "error": f"El evento con ID {event_id} no fue encontrado para actualizar."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = EventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(
            {
                "error": "Error de validación al actualizar el evento.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        summary="Eliminar un evento",
        description="Elimina el evento y todas sus subtareas en cascada.",
        responses={200: dict, 404: dict},
    )
    def delete(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {
                    "error": f"El evento con ID {event_id} no fue encontrado para eliminar."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        event.delete()
        return Response(
            {"message": f"Evento '{event.name}' eliminado exitosamente."},
            status=status.HTTP_200_OK,
        )


class EventSubtaskListCreateAPIView(APIView):
    """Gestión de subtareas logísticas asociadas a un evento."""

    def _get_event(self, request, event_id):
        user = request.user
        try:
            return Event.objects.get(id=event_id, user=user)
        except Event.DoesNotExist:
            return None

    @extend_schema(
        summary="Listar subtareas de un evento",
        description="Obtiene todas las gestiones logísticas pertenecientes a un evento.",
        responses={200: LogisticSubtaskSerializer(many=True), 404: dict},
    )
    def get(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {
                    "error": f"El evento con ID {event_id} no existe o no pertenece al usuario."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        subtasks = event.subtasks.all()
        serializer = LogisticSubtaskSerializer(subtasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Crear una subtarea en un evento",
        description="Crea una gestión logística dentro del evento indicado.",
        request=LogisticSubtaskSerializer,
        responses={201: LogisticSubtaskSerializer, 400: dict, 404: dict},
    )
    def post(self, request, event_id):
        event = self._get_event(request, event_id)
        if not event:
            return Response(
                {
                    "error": f"No se puede crear la subtarea: el evento con ID {event_id} no existe o no pertenece al usuario."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LogisticSubtaskSerializer(data=request.data, context={"event": event})
        if serializer.is_valid():
            serializer.save(event=event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {
                "error": "Datos inválidos para la subtarea logística.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SubtaskDetailAPIView(APIView):
    """Gestión individual de una subtarea (consultar, modificar o eliminar)."""

    def _get_subtask(self, request, subtask_id):
        user = request.user
        try:
            return LogisticSubtask.objects.get(id=subtask_id, event__user=user)
        except LogisticSubtask.DoesNotExist:
            return None

    @extend_schema(
        summary="Obtener detalle de una subtarea",
        description="Consulta los datos de una subtarea logística específica.",
        responses={200: LogisticSubtaskSerializer, 404: dict},
    )
    def get(self, request, subtask_id):
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {
                    "error": f"La subtarea logística con ID {subtask_id} no fue encontrada."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LogisticSubtaskSerializer(subtask)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar parcialmente una subtarea",
        description="Permite reprogramar fechas, actualizar estado (hecho/pospuesto), horas estimadas o notas.",
        request=LogisticSubtaskSerializer,
        responses={200: LogisticSubtaskSerializer, 400: dict, 404: dict},
    )
    def patch(self, request, subtask_id):
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {
                    "error": f"La subtarea con ID {subtask_id} no existe o no tiene permisos para modificarla."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = request.data.copy()
        payload.pop("event", None)

        serializer = LogisticSubtaskSerializer(subtask, data=payload, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(
            {
                "error": "Error de validación al actualizar la subtarea.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        summary="Eliminar una subtarea",
        description="Elimina la gestión logística especificada.",
        responses={200: dict, 404: dict},
    )
    def delete(self, request, subtask_id):
        subtask = self._get_subtask(request, subtask_id)
        if not subtask:
            return Response(
                {
                    "error": f"La subtarea con ID {subtask_id} no fue encontrada para eliminar."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        subtask.delete()
        return Response(
            {"message": f"Subtarea '{subtask.name}' eliminada correctamente."},
            status=status.HTTP_200_OK,
        )


class TodayAPIView(APIView):
    """Gestiones del usuario agrupadas en vencidas / para hoy / próximas (US-04, PI-54)."""

    def _base_queryset(self, user, filters):
        """
        Queryset de la vista Hoy: filtros validados (US-05) + orden de la US-04.

        Los filtros solo reducen el conjunto; el orden se define aquí y la
        agrupación se hace después, así que ninguno de los dos se altera.
        """
        subtasks = (
            LogisticSubtask.objects.filter(event__user=user)
            .exclude(status=LogisticSubtask.Status.DONE)
            .select_related("event")
            .order_by("scheduled_date", "estimated_hours", "id")
        )

        if "event" in filters:
            subtasks = subtasks.filter(event_id=filters["event"])

        if "status" in filters:
            subtasks = subtasks.filter(status=filters["status"])

        return subtasks

    @extend_schema(
        summary="Vista Hoy",
        description="Devuelve las gestiones agrupadas en vencidas, para hoy y próximas "
        "(ventana de 7 días), con filtros opcionales por evento y por estado.",
        parameters=[
            OpenApiParameter(
                "event",
                int,
                required=False,
                description="ID del evento por el que filtrar.",
            ),
            OpenApiParameter(
                "status",
                str,
                required=False,
                enum=LogisticSubtask.Status.values,
                description="Estado de la gestión por el que filtrar.",
            ),
        ],
        responses={200: dict, 400: dict},
    )
    def get(self, request):
        user = request.user
        today = timezone.localdate()

        filters = TodayFilterSerializer(data=request.query_params)
        if not filters.is_valid():
            return Response(
                {
                    "error": "Parámetros de filtro inválidos.",
                    "details": filters.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        subtasks = self._base_queryset(user, filters.validated_data)

        overdue = subtasks.overdue(today)
        due_today = subtasks.filter(scheduled_date=today)
        upcoming = subtasks.upcoming(today)

        return Response(
            {
                "today": today.isoformat(),
                "upcoming_window_days": UPCOMING_WINDOW_DAYS,
                "overdue": TodaySubtaskSerializer(overdue, many=True).data,
                "due_today": TodaySubtaskSerializer(due_today, many=True).data,
                "upcoming": TodaySubtaskSerializer(upcoming, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


INVALID_CREDENTIALS_MESSAGE = "Credenciales inválidas"


class LoginAPIView(APIView):
    """Inicio de sesión local con correo y contraseña (US-11, PI-166)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Iniciar sesión",
        description="Autentica al organizador con correo y contraseña e inicia su sesión. "
        "Ante credenciales incorrectas responde siempre con el mismo mensaje genérico.",
        request=LoginSerializer,
        responses={200: dict, 400: dict, 401: dict},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": "Datos inválidos para iniciar sesión.",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        candidate = User.objects.filter(email__iexact=email).first()
        user = None
        if candidate is not None:
            user = authenticate(request, username=candidate.username, password=password)
        else:
            # Gasta el mismo tiempo que una verificación real para no delatar
            # si el correo existe.
            User().set_password(password)

        if user is None:
            return Response(
                {"error": INVALID_CREDENTIALS_MESSAGE},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return Response(
            {
                "message": "Inicio de sesión exitoso.",
                "user": AuthUserSerializer(user).data,
                "csrf_token": get_token(request),
            },
            status=status.HTTP_200_OK,
        )


class RegisterAPIView(APIView):
    """Registro de un organizador con nombre, apellido, correo y contraseña (US-11)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Crear cuenta",
        description="Registra al organizador y deja su sesión iniciada. "
        "Responde con el usuario y el token CSRF para las siguientes peticiones.",
        request=RegisterSerializer,
        responses={201: dict, 400: dict},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": "Datos inválidos para crear la cuenta.",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()
        login(request, user)
        return Response(
            {
                "message": "Cuenta creada exitosamente.",
                "user": AuthUserSerializer(user).data,
                "csrf_token": get_token(request),
            },
            status=status.HTTP_201_CREATED,
        )


class MeAPIView(APIView):
    """Organizador de la sesión actual; el frontend lo usa al recargar la página."""

    @extend_schema(
        summary="Usuario actual",
        description="Devuelve el organizador autenticado y el token CSRF vigente. "
        "Responde 401 si no hay sesión.",
        responses={200: dict, 401: dict},
    )
    def get(self, request):
        return Response(
            {
                "user": AuthUserSerializer(request.user).data,
                "csrf_token": get_token(request),
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    """Cierra la sesión del organizador."""

    @extend_schema(
        summary="Cerrar sesión",
        description="Termina la sesión actual. Requiere el encabezado X-CSRFToken.",
        responses={200: dict, 401: dict},
    )
    def post(self, request):
        logout(request)
        return Response({"message": "Sesión cerrada."}, status=status.HTTP_200_OK)

