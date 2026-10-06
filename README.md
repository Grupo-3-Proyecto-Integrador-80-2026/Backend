# Backend — Organizador de Eventos Independientes

API en Django + Django REST Framework para el Mini-proyecto 1 del curso
Proyecto Integrador I (750018C, 2026-II), Universidad del Valle.

## Stack

- Django + Django REST Framework
- PostgreSQL (Supabase)
- django-cors-headers
- gunicorn + whitenoise (despliegue)
- Autenticación: sistema de usuarios de Django (modelo `User` extendido)

## Setup local

1. `git clone https://github.com/Grupo-3-Proyecto-Integrador-80-2026/Backend.git`
2. `python -m venv venv`
3. `source venv/Scripts/activate` (Windows) o `source venv/bin/activate` (Mac/Linux)
4. `pip install -r requirements.txt`
5. Copia `.env.example` a `.env` y pide los valores reales:
```
   cp .env.example .env
```
6. `python manage.py migrate`
7. `python manage.py runserver`

### Datos de ejemplo

Para tener eventos y gestiones de prueba (vencidas, para hoy y próximas) en tu cuenta (créala antes desde la app):

```
python manage.py cargar_datos_demo --email tu@correo.com           # solo si la cuenta no tiene eventos
python manage.py cargar_datos_demo --email tu@correo.com --reset   # reemplaza los eventos de esa cuenta
```

Las fechas se calculan a partir del día en que se ejecuta. El comando solo modifica datos de la cuenta indicada; revisa a qué base apunta tu `DATABASE_URL` antes de correrlo.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health/` | Verifica que la API esté corriendo |
GET | `/api/db-test/` | Verifica la conexión con la base de datos y consulta el primer usuario registrado
| PATCH | `/api/subtasks/:id/` | Reprograma o edita una gestión. Responde **409** si el día destino supera el límite diario (ver abajo) |
| GET | `/api/settings/daily-limit/` | Límite diario de horas de gestión del organizador (6 por defecto) |
| PATCH | `/api/settings/daily-limit/` | Actualiza el límite diario (`{"daily_hours_limit": 4}`, entero de 1 a 16) |

### Conflicto por sobrecarga diaria (US-07 / US-08)

Al cambiar la fecha, las horas o reactivar una gestión, el backend suma las horas de las gestiones
pendientes o en progreso del organizador para ese día. Si el total **supera** su límite, no guarda y responde:

```json
HTTP 409
{
  "error": "Quedarías con 7h de gestión planificadas (límite 6h).",
  "details": {
    "conflict": "daily_overload",
    "date": "2026-10-08",
    "planned_hours": 5.0,
    "subtask_hours": 2.0,
    "resulting_hours": 7.0,
    "limit_hours": 6,
    "excess_hours": 1.0,
    "message": "Quedarías con 7h de gestión planificadas (límite 6h).",
    "suggested_dates": ["2026-10-07", "2026-10-09", "2026-10-10"],
    "options": [
      {"action": "move", "label": "Mover la gestión a otro día"},
      {"action": "reduce_hours", "label": "Reducir las horas estimadas"},
      {"action": "postpone", "label": "Posponer la gestión"}
    ]
  }
}
```

Campos de control opcionales en el cuerpo del PATCH (no se guardan en la gestión):

- `"confirm_overload": true` — guarda el cambio aunque haya sobrecarga.
- `"resolution": "reduce_hours"` — exige que `estimated_hours` sea mayor que 0 y menor que las horas actuales; si aún excede el límite vuelve a responder 409 con las cifras nuevas.

Para resolver: mover = PATCH con una de `suggested_dates`; posponer = PATCH con `"status": "postponed"` (las gestiones hechas o pospuestas no suman carga).

## Despliegue

- API en producción: https://backend-eventos-csrw.onrender.com
- Health check: https://backend-eventos-csrw.onrender.com/api/health/