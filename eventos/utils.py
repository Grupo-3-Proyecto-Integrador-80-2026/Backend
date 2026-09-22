"""
Módulo de utilidades transversales para la aplicación de eventos.
"""

from .models import User

DEMO_USERNAME = "demo_user"
DEMO_EMAIL = "demo@eventos.com"


def resolve_request_user(request) -> User:
    """
    Obtiene el usuario actual de la petición.

    Reglas de negocio:
    - Si el usuario está autenticado (Sprint 2+), retorna request.user.
    - Si la petición es anónima (Sprint 0-1), resuelve o crea un usuario demo
      persistido para garantizar la integridad referencial sin bloquear el avance.
    """
    if request.user and request.user.is_authenticated:
        return request.user

    user, _ = User.objects.get_or_create(
        username=DEMO_USERNAME,
        defaults={
            "email": DEMO_EMAIL,
            "daily_hours_limit": 6,
            "first_name": "Usuario",
            "last_name": "Demo"
        }
    )
    return user