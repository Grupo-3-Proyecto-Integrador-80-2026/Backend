from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """
    Autenticación por sesión de Django que responde 401 (y no 403) cuando
    no hay sesión. DRF solo usa 401 si la clase define authenticate_header.
    """

    def authenticate_header(self, request):
        return "Session"