from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.views import exception_handler

NOT_AUTHENTICATED_MESSAGE = "Debes iniciar sesión para acceder a este recurso."


def api_exception_handler(exc, context):
    """Mantiene el formato {"error": ...} de la API también en los 401."""
    response = exception_handler(exc, context)
    if response is not None and isinstance(
        exc, (NotAuthenticated, AuthenticationFailed)
    ):
        response.data = {"error": NOT_AUTHENTICATED_MESSAGE}
    return response