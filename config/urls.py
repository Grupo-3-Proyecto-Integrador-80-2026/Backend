from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('eventos.urls')),

    # Rutas de Swagger / OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Errores fuera de las vistas de DRF (rutas inexistentes, fallos inesperados)
# con el mismo formato {"error": ...} de la API (TS-03).
handler404 = "eventos.exceptions.json_not_found"
handler500 = "eventos.exceptions.json_server_error"
