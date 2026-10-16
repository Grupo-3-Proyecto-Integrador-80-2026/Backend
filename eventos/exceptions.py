"""
Formato único de errores de la API (TS-03).

Toda respuesta de error sale como {"error": "<mensaje para la UI>"} y, si hay
errores por campo, también {"details": {campo: [mensajes]}}. Los mensajes están
en español y sin jerga técnica: el frontend los muestra tal cual.
"""

from django.http import Http404, JsonResponse
from rest_framework import exceptions
from rest_framework.views import exception_handler

NOT_AUTHENTICATED_MESSAGE = "Debes iniciar sesión para acceder a este recurso."
VALIDATION_MESSAGE = "Algunos datos no son válidos. Revísalos e inténtalo de nuevo."
CSRF_MESSAGE = (
    "Tu sesión expiró o la página quedó desactualizada. "
    "Recarga la página e inténtalo de nuevo."
)
NOT_FOUND_MESSAGE = "No encontramos lo que buscas. Es posible que se haya eliminado."
SERVER_ERROR_MESSAGE = (
    "Ocurrió un problema en el servidor. Inténtalo de nuevo en unos minutos."
)

# Mensaje por tipo de excepción de DRF (se revisan en orden)
EXCEPTION_MESSAGES = (
    (
        exceptions.ParseError,
        "No pudimos leer los datos enviados. Revisa el formulario e inténtalo de nuevo.",
    ),
    (
        exceptions.UnsupportedMediaType,
        "El formato de los datos enviados no es compatible. Deben enviarse como JSON.",
    ),
    (exceptions.MethodNotAllowed, "Esta acción no está disponible para este recurso."),
    (exceptions.NotAcceptable, "No podemos responder en el formato solicitado."),
    (exceptions.PermissionDenied, "No tienes permiso para realizar esta acción."),
    (exceptions.NotFound, NOT_FOUND_MESSAGE),
    (exceptions.Throttled, "Hiciste demasiados intentos. Espera un momento e inténtalo de nuevo."),
)


def _message_for(exc):
    if isinstance(exc, exceptions.PermissionDenied) and str(exc.detail).startswith("CSRF Failed"):
        return CSRF_MESSAGE
    if isinstance(exc, Http404):
        return NOT_FOUND_MESSAGE
    for exc_class, message in EXCEPTION_MESSAGES:
        if isinstance(exc, exc_class):
            return message
    return SERVER_ERROR_MESSAGE


def api_exception_handler(exc, context):
    """Convierte cualquier error de DRF al formato {"error", "details"?} de la API."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.data = {"error": NOT_AUTHENTICATED_MESSAGE}
    elif isinstance(exc, exceptions.ValidationError):
        details = response.data
        if not isinstance(details, dict):
            details = {"non_field_errors": details}
        response.data = {"error": VALIDATION_MESSAGE, "details": details}
    else:
        response.data = {"error": _message_for(exc)}
    return response


def json_not_found(request, exception=None):
    """handler404: las rutas inexistentes también responden en el formato de la API."""
    return JsonResponse({"error": NOT_FOUND_MESSAGE}, status=404)


def json_server_error(request):
    """handler500: un fallo inesperado no muestra la página de error de Django."""
    return JsonResponse({"error": SERVER_ERROR_MESSAGE}, status=500)


def json_csrf_failure(request, reason=""):
    """
    CSRF_FAILURE_VIEW: el rechazo del middleware de CSRF (vistas que no son de DRF,
    como /api/health/) responde en el formato de la API en vez de la página HTML.
    """
    return JsonResponse({"error": CSRF_MESSAGE}, status=403)
