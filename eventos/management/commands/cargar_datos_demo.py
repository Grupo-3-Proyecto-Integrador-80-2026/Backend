"""
Carga eventos y gestiones logísticas de ejemplo para un organizador.

Las fechas se calculan relativas al día en que se ejecuta, de modo que la
vista "Hoy" siempre tenga gestiones vencidas, para hoy y próximas.

Uso:
    python manage.py cargar_datos_demo --email laura@correo.com           # a una cuenta existente
    python manage.py cargar_datos_demo --email laura@correo.com --reset   # reemplaza sus eventos
    python manage.py cargar_datos_demo                                     # al usuario demo (sin contraseña)

Solo modifica datos del organizador elegido; nunca toca eventos de otros usuarios.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from eventos.models import Event, LogisticSubtask, User

Type = LogisticSubtask.TaskType
Status = LogisticSubtask.Status
Priority = LogisticSubtask.Priority

DEMO_USERNAME = "demo_user"
DEMO_EMAIL = "demo@eventos.com"

# Cada gestión: (nombre, tipo, días respecto a hoy, horas, prioridad, estado, nota)
DEMO_EVENTS = [
    {
        "name": "Boda de Laura y Andrés",
        "event_type": Event.EventType.WEDDING,
        "contact": "Laura Gómez - 300 123 4567",
        "location": "Hacienda El Paraíso, Jamundí",
        "event_offset": 30,
        "status": Event.Status.IN_PROGRESS,
        "description": "Ceremonia y recepción para 150 invitados. Decoración en tonos blanco y verde.",
        "subtasks": [
            ("Reservar el salón principal", Type.BOOK_VENUE, -5, "3.0", Priority.HIGH, Status.PENDING, "El salón pidió anticipo del 30 %."),
            ("Confirmar menú con el catering", Type.CONFIRM_CATERING, 0, "2.0", Priority.HIGH, Status.IN_PROGRESS, None),
            ("Enviar invitaciones impresas", Type.SEND_INVITATIONS, 3, "2.0", Priority.MEDIUM, Status.PENDING, None),
            ("Contratar fotógrafo y video", Type.COORDINATE_VENDORS, 6, "1.5", Priority.MEDIUM, Status.PENDING, None),
            ("Prueba de menú con los novios", Type.CONFIRM_CATERING, 18, "2.0", Priority.LOW, Status.PENDING, None),
            ("Definir paleta de decoración", Type.OTHER, -10, "1.0", Priority.LOW, Status.DONE, "Aprobada por la novia."),
        ],
    },
    {
        "name": "Lanzamiento Café Andino",
        "event_type": Event.EventType.CORPORATE,
        "contact": "Café Andino S.A.S. - mercadeo@cafeandino.co",
        "location": "Hotel Intercontinental, Cali",
        "event_offset": 12,
        "status": Event.Status.PLANNING,
        "description": "Presentación de la nueva línea de cafés especiales para 80 clientes y prensa.",
        "subtasks": [
            ("Coordinar proveedor de sonido", Type.COORDINATE_VENDORS, -2, "2.0", Priority.HIGH, Status.POSTPONED, "El proveedor no responde; buscar alternativa."),
            ("Enviar invitaciones digitales", Type.SEND_INVITATIONS, 0, "1.0", Priority.MEDIUM, Status.PENDING, None),
            ("Confirmar fotógrafo", Type.COORDINATE_VENDORS, 3, "0.5", Priority.MEDIUM, Status.PENDING, None),
            ("Reservar auditorio", Type.BOOK_VENUE, -1, "1.0", Priority.HIGH, Status.DONE, None),
            ("Confirmar coffee break", Type.CONFIRM_CATERING, 9, "1.5", Priority.MEDIUM, Status.PENDING, None),
        ],
    },
    {
        "name": "Cumpleaños 15 de Sofía",
        "event_type": Event.EventType.BIRTHDAY,
        "contact": "Marta Ruiz (mamá) - 315 987 6543",
        "location": "Salón Los Almendros, Palmira",
        "event_offset": 45,
        "status": Event.Status.PLANNING,
        "description": "Fiesta de quince años con 100 invitados, temática jardín.",
        "subtasks": [
            ("Cotizar decoración temática", Type.OTHER, 1, "1.5", Priority.MEDIUM, Status.PENDING, None),
            ("Reservar salón de eventos", Type.BOOK_VENUE, 5, "2.0", Priority.HIGH, Status.PENDING, None),
            ("Contratar DJ", Type.COORDINATE_VENDORS, 20, "1.0", Priority.LOW, Status.PENDING, None),
        ],
    },
    {
        "name": "Cena de exalumnos Promoción 2016",
        "event_type": Event.EventType.SOCIAL,
        "contact": "Comité de exalumnos - exalumnos2016@gmail.com",
        "location": "Restaurante El Mirador, Cali",
        "event_offset": 8,
        "status": Event.Status.IN_PROGRESS,
        "description": "Reencuentro de 10 años, cena para 40 personas.",
        "subtasks": [
            ("Confirmar asistentes", Type.SEND_INVITATIONS, -3, "1.0", Priority.MEDIUM, Status.PENDING, None),
            ("Separar mesas en el restaurante", Type.BOOK_VENUE, 0, "0.5", Priority.HIGH, Status.PENDING, None),
            ("Elegir menú de la cena", Type.CONFIRM_CATERING, 2, "1.0", Priority.MEDIUM, Status.PENDING, None),
        ],
    },
    {
        "name": "Feria de emprendimiento Univalle",
        "event_type": Event.EventType.OTHER,
        "contact": "Bienestar Universitario",
        "location": "Plazoleta de Ingeniería, Universidad del Valle",
        "event_offset": 25,
        "status": Event.Status.PLANNING,
        "description": "Feria con 20 stands de emprendedores estudiantiles.",
        "subtasks": [
            ("Solicitar permiso de uso de la plazoleta", Type.BOOK_VENUE, 4, "2.5", Priority.HIGH, Status.PENDING, None),
            ("Convocar emprendedores", Type.SEND_INVITATIONS, 10, "3.0", Priority.MEDIUM, Status.PENDING, None),
        ],
    },
]


class Command(BaseCommand):
    help = "Carga eventos y gestiones de ejemplo para el usuario demo (fechas relativas a hoy)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Correo de una cuenta existente que recibirá los datos (por defecto, el usuario demo).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina los eventos actuales del organizador antes de cargar los de ejemplo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["email"]:
            user = User.objects.filter(email__iexact=options["email"]).first()
            if user is None:
                raise CommandError(
                    f"No existe una cuenta con el correo {options['email']}. Créala primero desde la app."
                )
        else:
            user, _ = User.objects.get_or_create(
                username=DEMO_USERNAME,
                defaults={"email": DEMO_EMAIL, "daily_hours_limit": 6, "first_name": "Usuario", "last_name": "Demo"},
            )

        existing = Event.objects.filter(user=user)
        if existing.exists():
            if not options["reset"]:
                raise CommandError(
                    f"'{user.email}' ya tiene {existing.count()} evento(s). "
                    "Usa --reset para reemplazarlos por los datos de ejemplo."
                )
            deleted = existing.count()
            existing.delete()
            self.stdout.write(f"Eliminados {deleted} evento(s) previos de '{user.email}'.")

        today = timezone.localdate()
        total_subtasks = 0
        for data in DEMO_EVENTS:
            event = Event.objects.create(
                user=user,
                name=data["name"],
                event_type=data["event_type"],
                contact=data["contact"],
                location=data["location"],
                event_date=today + timedelta(days=data["event_offset"]),
                status=data["status"],
                description=data["description"],
            )
            LogisticSubtask.objects.bulk_create(
                LogisticSubtask(
                    event=event,
                    name=name,
                    type=task_type,
                    scheduled_date=today + timedelta(days=offset),
                    estimated_hours=Decimal(hours),
                    priority=priority,
                    status=task_status,
                    note=note,
                )
                for name, task_type, offset, hours, priority, task_status, note in data["subtasks"]
            )
            total_subtasks += len(data["subtasks"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Cargados {len(DEMO_EVENTS)} eventos y {total_subtasks} gestiones de ejemplo "
                f"para '{user.username}' (fechas relativas a {today.isoformat()})."
            )
        )
