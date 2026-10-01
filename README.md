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

Para tener eventos y gestiones de prueba (vencidas, para hoy y próximas) en el usuario demo:

```
python manage.py cargar_datos_demo           # solo si el usuario demo no tiene eventos
python manage.py cargar_datos_demo --reset   # reemplaza los eventos del usuario demo
```

Las fechas se calculan a partir del día en que se ejecuta. El comando solo modifica datos del usuario demo; revisa a qué base apunta tu `DATABASE_URL` antes de correrlo.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health/` | Verifica que la API esté corriendo |
GET | `/api/db-test/` | Verifica la conexión con la base de datos y consulta el primer usuario registrado

## Despliegue

- API en producción: https://backend-eventos-csrw.onrender.com
- Health check: https://backend-eventos-csrw.onrender.com/api/health/