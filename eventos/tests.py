from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import Event, LogisticSubtask, User

import json

class OverdueConditionTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        user = User.objects.create_user("demo_user", password="x")
        self.event = Event.objects.create(
            user=user, name="Evento", event_date=self.today
        )

    def make(self, days, status="pending"):
        return LogisticSubtask.objects.create(
            event=self.event,
            name=f"t{days}",
            scheduled_date=self.today + timedelta(days=days),
            status=status,
        )

    def test_yesterday_is_overdue(self):
        self.assertTrue(self.make(-1).is_overdue)

    def test_today_is_not_overdue(self):
        self.assertFalse(self.make(0).is_overdue)

    def test_future_is_not_overdue(self):
        self.assertFalse(self.make(3).is_overdue)

    def test_done_is_never_overdue(self):
        self.assertFalse(self.make(-5, status="done").is_overdue)

    def test_queryset_matches_property(self):
        for d in (-3, -1, 0, 2):
            self.make(d)
        self.make(-4, status="done")
        from_qs = set(LogisticSubtask.objects.overdue().values_list("id", flat=True))
        from_prop = {t.id for t in LogisticSubtask.objects.all() if t.is_overdue}
        self.assertEqual(from_qs, from_prop)


class TodayTieBreakTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        user = User.objects.create_user("demo_user", password="x")
        self.client.force_login(user)
        self.event = Event.objects.create(
            user=user, name="Evento", event_date=self.today
        )

    def make(self, name, days, hours):
        return LogisticSubtask.objects.create(
            event=self.event,
            name=name,
            scheduled_date=self.today + timedelta(days=days),
            estimated_hours=hours,
        )

    def names(self, group):
        return [t["name"] for t in self.client.get("/api/today/").json()[group]]

    def test_tie_in_overdue_orders_by_hours(self):
        self.make("larga", -2, "4.0")
        self.make("corta", -2, "0.5")
        self.assertEqual(self.names("overdue"), ["corta", "larga"])

    def test_tie_due_today_orders_by_hours(self):
        self.make("larga", 0, "3.0")
        self.make("corta", 0, "1.0")
        self.assertEqual(self.names("due_today"), ["corta", "larga"])

    def test_tie_in_upcoming_orders_by_hours(self):
        self.make("larga", 2, "5.0")
        self.make("corta", 2, "1.5")
        self.assertEqual(self.names("upcoming"), ["corta", "larga"])

    def test_date_takes_precedence_over_hours(self):
        self.make("lejana_corta", 4, "0.5")
        self.make("cercana_larga", 1, "8.0")
        self.assertEqual(self.names("upcoming"), ["cercana_larga", "lejana_corta"])


class FiltersPreserveGroupingAndOrderTests(TestCase):
    GROUPS = ("overdue", "due_today", "upcoming")

    def setUp(self):
        self.today = timezone.localdate()
        user = User.objects.create_user("demo_user", password="x")
        self.client.force_login(user)
        self.ev1 = Event.objects.create(
            user=user, name="Evento 1", event_date=self.today
        )
        self.ev2 = Event.objects.create(
            user=user, name="Evento 2", event_date=self.today
        )
        # (evento, nombre, días desde hoy, horas, estado)
        rows = [
            (self.ev1, "o1", -3, "2.0", "pending"),
            (self.ev1, "o2", -3, "1.0", "in_progress"),  # empate con o1
            (self.ev2, "o3", -1, "1.0", "pending"),
            (self.ev1, "h1", 0, "3.0", "pending"),
            (self.ev2, "h2", 0, "1.0", "in_progress"),
            (self.ev1, "u1", 2, "1.0", "pending"),
            (self.ev1, "u2", 2, "0.5", "postponed"),  # empate con u1
            (self.ev2, "u3", 3, "2.0", "postponed"),
            (self.ev2, "u4", 1, "1.0", "pending"),
        ]
        for event, name, days, hours, status in rows:
            LogisticSubtask.objects.create(
                event=event,
                name=name,
                scheduled_date=self.today + timedelta(days=days),
                estimated_hours=hours,
                status=status,
            )

    def groups(self, query=""):
        data = self.client.get(f"/api/today/{query}").json()
        return {g: [t["name"] for t in data[g]] for g in self.GROUPS}

    def assert_filter_only_removes(self, query, matching_names):
        """El resultado filtrado == el sin filtrar, quitando lo que no coincide."""
        unfiltered = self.groups()
        expected = {
            g: [n for n in unfiltered[g] if n in matching_names] for g in self.GROUPS
        }
        self.assertEqual(self.groups(query), expected)

    def test_unfiltered_baseline_order(self):
        self.assertEqual(
            self.groups(),
            {
                "overdue": ["o2", "o1", "o3"],
                "due_today": ["h2", "h1"],
                "upcoming": ["u4", "u2", "u1", "u3"],
            },
        )

    def test_event_filter_keeps_groups_and_order(self):
        names = set(
            LogisticSubtask.objects.filter(event=self.ev1).values_list(
                "name", flat=True
            )
        )
        self.assert_filter_only_removes(f"?event={self.ev1.id}", names)

    def test_status_filter_keeps_groups_and_order(self):
        names = set(
            LogisticSubtask.objects.filter(status="pending").values_list(
                "name", flat=True
            )
        )
        self.assert_filter_only_removes("?status=pending", names)

    def test_combined_filter_keeps_groups_and_order(self):
        names = set(
            LogisticSubtask.objects.filter(
                event=self.ev1, status="pending"
            ).values_list("name", flat=True)
        )
        self.assert_filter_only_removes(f"?event={self.ev1.id}&status=pending", names)

    def test_tie_break_survives_filtering(self):
        groups = self.groups(f"?event={self.ev1.id}")
        self.assertEqual(groups["overdue"], ["o2", "o1"])
        self.assertEqual(groups["upcoming"], ["u2", "u1"])

    def test_filtered_response_keeps_same_shape(self):
        plain = self.client.get("/api/today/").json()
        filtered = self.client.get("/api/today/?status=pending").json()
        self.assertEqual(plain.keys(), filtered.keys())


class TodayFilterValidationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("demo_user", password="x")
        self.client.force_login(user)

    def get(self, query):
        return self.client.get(f"/api/today/{query}")

    def assert_invalid(self, query, *fields):
        response = self.get(query)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        for field in fields:
            self.assertIn(field, body["details"])

    def test_non_numeric_event_is_rejected(self):
        self.assert_invalid("?event=abc", "event")

    def test_decimal_event_is_rejected(self):
        self.assert_invalid("?event=1.5", "event")

    def test_zero_and_negative_event_are_rejected(self):
        self.assert_invalid("?event=0", "event")
        self.assert_invalid("?event=-3", "event")

    def test_unknown_status_is_rejected(self):
        self.assert_invalid("?status=xyz", "status")

    def test_both_invalid_report_both_fields(self):
        self.assert_invalid("?event=abc&status=xyz", "event", "status")

    def test_valid_params_return_200(self):
        self.assertEqual(self.get("?event=1&status=pending").status_code, 200)

    def test_empty_params_are_ignored(self):
        self.assertEqual(self.get("?event=&status=").status_code, 200)

    def test_nonexistent_event_returns_empty_groups(self):
        response = self.get("?event=999")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            (data["overdue"], data["due_today"], data["upcoming"]), ([], [], [])
        )


class LoginTests(TestCase):
    URL = "/api/auth/login/"

    def setUp(self):
        self.user = User.objects.create_user(
            "elena",
            email="elena@eventos.com",
            password="Secreta123",
            first_name="Elena",
            last_name="Morales",
        )

    def post(self, payload):
        return self.client.post(self.URL, payload, content_type="application/json")

    def test_login_success(self):
        response = self.post({"email": "elena@eventos.com", "password": "Secreta123"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user"]["email"], "elena@eventos.com")
        self.assertNotIn("password", body["user"])
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_email_is_case_insensitive(self):
        response = self.post({"email": "ELENA@eventos.com", "password": "Secreta123"})
        self.assertEqual(response.status_code, 200)

    def test_wrong_password_returns_generic_error(self):
        response = self.post({"email": "elena@eventos.com", "password": "otra"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Credenciales inválidas"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_email_is_indistinguishable_from_wrong_password(self):
        wrong_password = self.post({"email": "elena@eventos.com", "password": "otra"})
        unknown_email = self.post({"email": "nadie@eventos.com", "password": "otra"})
        self.assertEqual(wrong_password.status_code, unknown_email.status_code)
        self.assertEqual(wrong_password.json(), unknown_email.json())

    def test_inactive_user_gets_same_generic_error(self):
        self.user.is_active = False
        self.user.save()
        response = self.post({"email": "elena@eventos.com", "password": "Secreta123"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Credenciales inválidas"})

    def test_missing_fields_are_rejected(self):
        response = self.post({})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("email", body["details"])
        self.assertIn("password", body["details"])

    def test_malformed_email_is_rejected(self):
        response = self.post({"email": "no-es-un-correo", "password": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["details"])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)


class AuthRequiredTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "elena", email="elena@eventos.com", password="Secreta123"
        )
        today = timezone.localdate()
        self.event = Event.objects.create(user=self.user, name="E", event_date=today)
        self.subtask = LogisticSubtask.objects.create(
            event=self.event, name="s", scheduled_date=today
        )

    def protected_endpoints(self):
        e, s = self.event.id, self.subtask.id
        return [
            ("GET", "/api/events/"),
            ("POST", "/api/events/"),
            ("GET", f"/api/events/{e}/"),
            ("PATCH", f"/api/events/{e}/"),
            ("DELETE", f"/api/events/{e}/"),
            ("GET", f"/api/events/{e}/subtasks/"),
            ("POST", f"/api/events/{e}/subtasks/"),
            ("GET", f"/api/subtasks/{s}/"),
            ("PATCH", f"/api/subtasks/{s}/"),
            ("DELETE", f"/api/subtasks/{s}/"),
            ("GET", "/api/today/"),
            ("GET", "/api/settings/daily-limit/"),
            ("PATCH", "/api/settings/daily-limit/"),
        ]

    def request(self, method, url):
        return self.client.generic(
            method, url, data="{}", content_type="application/json"
        )

    def test_protected_endpoints_return_401_without_session(self):
        for method, url in self.protected_endpoints():
            with self.subTest(method=method, url=url):
                self.assertEqual(self.request(method, url).status_code, 401)

    def test_401_uses_standard_error_body(self):
        response = self.request("GET", "/api/events/")
        self.assertEqual(
            response.json(),
            {"error": "Debes iniciar sesión para acceder a este recurso."},
        )

    def test_unauthenticated_requests_change_nothing(self):
        events, subtasks = Event.objects.count(), LogisticSubtask.objects.count()
        for method, url in self.protected_endpoints():
            self.request(method, url)
        self.assertEqual(Event.objects.count(), events)
        self.assertEqual(LogisticSubtask.objects.count(), subtasks)

    def test_authenticated_user_can_access(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/events/").status_code, 200)
        self.assertEqual(self.client.get("/api/today/").status_code, 200)

    def test_public_endpoints_stay_public(self):
        self.assertEqual(self.client.get("/api/health/").status_code, 200)
        # El login es accesible sin sesión: responde 400 por cuerpo vacío, no 401.
        self.assertEqual(self.request("POST", "/api/auth/login/").status_code, 400)


class DataIsolationTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.a = User.objects.create_user(
            "organizador_a", email="a@eventos.com", password="x"
        )
        self.b = User.objects.create_user(
            "organizador_b", email="b@eventos.com", password="x"
        )
        self.event_a = Event.objects.create(
            user=self.a, name="Evento de A", event_date=today
        )
        self.subtask_a = LogisticSubtask.objects.create(
            event=self.event_a,
            name="Gestión de A",
            scheduled_date=today - timedelta(days=1),
        )
        self.event_b = Event.objects.create(
            user=self.b, name="Evento de B", event_date=today
        )
        self.subtask_b = LogisticSubtask.objects.create(
            event=self.event_b, name="Gestión de B", scheduled_date=today
        )
        self.client.force_login(self.b)  # la sesión activa es la de B

    def json(self, method, url, payload=None):
        return self.client.generic(
            method, url, data=json.dumps(payload or {}), content_type="application/json"
        )

    # --- Eventos ---
    def test_each_user_sees_only_own_events(self):
        for user, expected in ((self.a, "Evento de A"), (self.b, "Evento de B")):
            self.client.force_login(user)
            names = [e["name"] for e in self.client.get("/api/events/").json()]
            self.assertEqual(names, [expected])

    def test_cannot_read_foreign_event(self):
        response = self.client.get(f"/api/events/{self.event_a.id}/")
        self.assertEqual(response.status_code, 404)

    def test_cannot_modify_foreign_event(self):
        response = self.json("PATCH", f"/api/events/{self.event_a.id}/", {"name": "x"})
        self.assertEqual(response.status_code, 404)
        self.event_a.refresh_from_db()
        self.assertEqual(self.event_a.name, "Evento de A")

    def test_cannot_delete_foreign_event(self):
        response = self.json("DELETE", f"/api/events/{self.event_a.id}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(id=self.event_a.id).exists())

    def test_created_event_belongs_to_authenticated_user(self):
        response = self.json(
            "POST",
            "/api/events/",
            {"name": "Nuevo", "event_date": "2026-12-01", "user": self.a.id},
        )
        self.assertEqual(response.status_code, 201)
        created = Event.objects.get(id=response.json()["id"])
        self.assertEqual(created.user, self.b)  # el "user" enviado se ignora

    # --- Gestiones ---
    def test_cannot_list_or_create_subtasks_in_foreign_event(self):
        url = f"/api/events/{self.event_a.id}/subtasks/"
        self.assertEqual(self.client.get(url).status_code, 404)
        response = self.json(
            "POST",
            url,
            {"name": "intruso", "type": "other", "scheduled_date": "2026-12-01"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.event_a.subtasks.count(), 1)

    def test_cannot_access_foreign_subtask(self):
        url = f"/api/subtasks/{self.subtask_a.id}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.json("PATCH", url, {"name": "x"}).status_code, 404)
        self.assertEqual(self.json("DELETE", url).status_code, 404)
        self.subtask_a.refresh_from_db()
        self.assertEqual(self.subtask_a.name, "Gestión de A")

    # --- Vista Hoy ---
    def test_today_only_includes_own_subtasks(self):
        data = self.client.get("/api/today/").json()
        names = [t["name"] for g in ("overdue", "due_today", "upcoming") for t in data[g]]
        self.assertEqual(names, ["Gestión de B"])
        self.assertEqual(data["overdue"], [])  # la vencida de A no aparece

    def test_today_filter_by_foreign_event_returns_nothing(self):
        data = self.client.get(f"/api/today/?event={self.event_a.id}").json()
        self.assertEqual(
            (data["overdue"], data["due_today"], data["upcoming"]), ([], [], [])
        )

    # --- No revelar existencia ---
    def test_foreign_resource_looks_like_nonexistent(self):
        foreign = self.client.get(f"/api/events/{self.event_a.id}/")
        missing = self.client.get("/api/events/999999/")
        self.assertEqual(foreign.status_code, missing.status_code)

    def test_db_test_does_not_expose_usernames(self):
        content = self.client.get("/api/db-test/").content.decode()
        self.assertNotIn("organizador", content)


class NoDemoUserTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            "elena", email="elena@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.organizer)

    def post(self, url, payload):
        return self.client.post(url, payload, content_type="application/json")

    def test_created_event_is_owned_by_authenticated_organizer(self):
        response = self.post(
            "/api/events/", {"name": "Boda", "event_date": "2026-12-01"}
        )
        self.assertEqual(response.status_code, 201)
        event = Event.objects.get(id=response.json()["id"])
        self.assertEqual(event.user, self.organizer)

    def test_created_subtask_belongs_to_authenticated_organizers_event(self):
        event = Event.objects.create(
            user=self.organizer, name="Boda", event_date=timezone.localdate()
        )
        response = self.post(
            f"/api/events/{event.id}/subtasks/",
            {
                "name": "Reservar salón",
                "type": "book_venue",
                "scheduled_date": event.event_date.isoformat(),
                "estimated_hours": 2,
            },
        )
        self.assertEqual(response.status_code, 201)
        subtask = LogisticSubtask.objects.get(id=response.json()["id"])
        self.assertEqual(subtask.event, event)
        self.assertEqual(subtask.event.user, self.organizer)

    def test_each_organizer_owns_what_they_create(self):
        other = User.objects.create_user(
            "marco", email="marco@eventos.com", password="Secreta123"
        )
        payload = {"name": "Evento", "event_date": "2026-12-01"}
        first = self.post("/api/events/", payload).json()["id"]
        self.client.force_login(other)
        second = self.post("/api/events/", payload).json()["id"]
        self.assertEqual(Event.objects.get(id=first).user, self.organizer)
        self.assertEqual(Event.objects.get(id=second).user, other)

    def test_demo_user_is_never_created_by_the_api(self):
        self.client.get("/api/events/")
        self.client.get("/api/today/")
        self.post("/api/events/", {"name": "Boda", "event_date": "2026-12-01"})
        self.assertFalse(User.objects.filter(username="demo_user").exists())

    def test_anonymous_requests_create_nothing_and_no_demo_user(self):
        self.client.logout()
        response = self.post(
            "/api/events/", {"name": "Boda", "event_date": "2026-12-01"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Event.objects.count(), 0)
        self.assertFalse(User.objects.filter(username="demo_user").exists())

class RegisterTests(TestCase):
    URL = "/api/auth/register/"
    VALID = {
        "first_name": "Laura",
        "last_name": "Gómez",
        "email": "Laura@Eventos.com",
        "password": "Organiza2026!",
    }

    def post(self, payload):
        return self.client.post(self.URL, payload, content_type="application/json")

    def test_register_creates_user_and_starts_session(self):
        response = self.post(self.VALID)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["user"]["email"], "laura@eventos.com")
        self.assertEqual(body["user"]["first_name"], "Laura")
        self.assertNotIn("password", body["user"])
        self.assertIn("csrf_token", body)
        user = User.objects.get(email="laura@eventos.com")
        self.assertTrue(user.check_password("Organiza2026!"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_registered_user_can_log_in(self):
        self.post(self.VALID)
        self.client.logout()
        response = self.client.post(
            "/api/auth/login/",
            {"email": "laura@eventos.com", "password": "Organiza2026!"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_is_rejected_case_insensitive(self):
        self.post(self.VALID)
        self.client.logout()
        response = self.post({**self.VALID, "email": "LAURA@eventos.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"]["email"], ["Ya existe una cuenta con este correo."]
        )

    def test_weak_password_is_rejected_in_spanish(self):
        response = self.post({**self.VALID, "password": "123"})
        self.assertEqual(response.status_code, 400)
        messages = " ".join(response.json()["details"]["password"])
        self.assertIn("contraseña", messages.lower())
        self.assertFalse(User.objects.filter(email="laura@eventos.com").exists())

    def test_missing_fields_are_rejected(self):
        response = self.post({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            set(response.json()["details"]),
            {"first_name", "last_name", "email", "password"},
        )


class SessionEndpointsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "elena@eventos.com", email="elena@eventos.com", password="Secreta123"
        )

    def test_me_requires_session(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_me_returns_user_and_csrf_token(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], "elena@eventos.com")
        self.assertTrue(response.json()["csrf_token"])

    def test_logout_ends_session(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)


class CsrfFlowTests(TestCase):
    """Con sesión por cookie, las escrituras exigen el token que entrega el login."""

    def setUp(self):
        from django.test import Client

        User.objects.create_user(
            "elena@eventos.com", email="elena@eventos.com", password="Secreta123"
        )
        self.client = Client(enforce_csrf_checks=True)
        login = self.client.post(
            "/api/auth/login/",
            {"email": "elena@eventos.com", "password": "Secreta123"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.token = login.json()["csrf_token"]
        self.event = {"name": "Boda", "event_date": "2026-12-01", "event_type": "wedding"}

    def test_write_without_csrf_token_is_rejected(self):
        response = self.client.post("/api/events/", self.event, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_write_with_login_csrf_token_succeeds(self):
        response = self.client.post(
            "/api/events/",
            self.event,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 201)


class EventDateNotInPastTests(TestCase):
    """La fecha de un evento no puede ser anterior a hoy (al crear ni al cambiarla)."""

    def setUp(self):
        self.user = User.objects.create_user(
            "elena@eventos.com", email="elena@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def post(self, date):
        return self.client.post(
            "/api/events/",
            {"name": "Boda", "event_date": date.isoformat()},
            content_type="application/json",
        )

    def test_past_date_is_rejected_on_create(self):
        response = self.post(self.today - timedelta(days=1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"]["event_date"],
            ["La fecha del evento no puede ser anterior a hoy."],
        )
        self.assertFalse(Event.objects.exists())

    def test_today_and_future_dates_are_allowed(self):
        self.assertEqual(self.post(self.today).status_code, 201)
        self.assertEqual(self.post(self.today + timedelta(days=30)).status_code, 201)

    def test_past_event_can_be_edited_keeping_its_date(self):
        past = self.today - timedelta(days=10)
        event = Event.objects.create(user=self.user, name="Pasado", event_date=past)
        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"name": "Pasado (editado)", "event_date": past.isoformat()},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_move_event_to_another_past_date(self):
        event = Event.objects.create(user=self.user, name="Boda", event_date=self.today)
        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"event_date": (self.today - timedelta(days=3)).isoformat()},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class SubtaskDateRangeTests(TestCase):
    """La fecha objetivo de una gestión debe estar entre hoy y la fecha del evento."""

    def setUp(self):
        self.user = User.objects.create_user(
            "elena@eventos.com", email="elena@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.event = Event.objects.create(
            user=self.user, name="Boda", event_date=self.today + timedelta(days=10)
        )

    def create(self, date):
        return self.client.post(
            f"/api/events/{self.event.id}/subtasks/",
            {"name": "Reservar salón", "scheduled_date": date.isoformat(), "estimated_hours": 2},
            content_type="application/json",
        )

    def test_dates_between_today_and_event_are_allowed(self):
        self.assertEqual(self.create(self.today).status_code, 201)
        self.assertEqual(self.create(self.today + timedelta(days=5)).status_code, 201)
        self.assertEqual(self.create(self.event.event_date).status_code, 201)

    def test_past_date_is_rejected(self):
        response = self.create(self.today - timedelta(days=1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"]["scheduled_date"],
            ["La fecha objetivo no puede ser anterior a hoy."],
        )

    def test_date_after_event_is_rejected(self):
        response = self.create(self.event.event_date + timedelta(days=1))
        self.assertEqual(response.status_code, 400)
        self.assertIn("posterior a la fecha del evento", response.json()["details"]["scheduled_date"][0])
        self.assertFalse(LogisticSubtask.objects.exists())

    def test_overdue_subtask_can_change_status_keeping_its_date(self):
        overdue = LogisticSubtask.objects.create(
            event=self.event, name="Vencida", scheduled_date=self.today - timedelta(days=3)
        )
        response = self.client.patch(
            f"/api/subtasks/{overdue.id}/",
            {"status": "done", "scheduled_date": overdue.scheduled_date.isoformat()},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_move_subtask_after_event_date(self):
        subtask = LogisticSubtask.objects.create(
            event=self.event, name="Gestión", scheduled_date=self.today
        )
        response = self.client.patch(
            f"/api/subtasks/{subtask.id}/",
            {"scheduled_date": (self.event.event_date + timedelta(days=2)).isoformat()},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class RescheduleSubtaskTests(TestCase):
    """US-06: reprogramar la fecha objetivo por PATCH y verla reagrupada en /hoy."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rosa@eventos.com", email="rosa@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.event = Event.objects.create(
            user=self.user, name="Boda", event_date=self.today + timedelta(days=10)
        )
        self.subtask = LogisticSubtask.objects.create(
            event=self.event,
            name="Buscar proveedores",
            scheduled_date=self.today - timedelta(days=2),
            estimated_hours="2.0",
        )

    def patch(self, payload, subtask_id=None):
        return self.client.patch(
            f"/api/subtasks/{subtask_id or self.subtask.id}/",
            payload,
            content_type="application/json",
        )

    def group_of(self, subtask_id):
        data = self.client.get("/api/today/").json()
        for group in ("overdue", "due_today", "upcoming"):
            if subtask_id in [t["id"] for t in data[group]]:
                return group
        return None

    def test_reschedule_to_today_moves_to_due_today(self):
        self.assertEqual(self.group_of(self.subtask.id), "overdue")
        response = self.patch({"scheduled_date": self.today.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scheduled_date"], self.today.isoformat())
        self.assertEqual(self.group_of(self.subtask.id), "due_today")

    def test_reschedule_to_future_moves_to_upcoming(self):
        target = self.today + timedelta(days=3)
        self.assertEqual(self.patch({"scheduled_date": target.isoformat()}).status_code, 200)
        self.assertEqual(self.group_of(self.subtask.id), "upcoming")

    def test_reschedule_persists(self):
        target = self.today + timedelta(days=3)
        self.patch({"scheduled_date": target.isoformat()})
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.scheduled_date, target)

    def test_invalid_date_format_returns_standard_error(self):
        response = self.patch({"scheduled_date": "31-02-2026"})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("scheduled_date", body["details"])
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.scheduled_date, self.today - timedelta(days=2))

    def test_empty_date_is_rejected(self):
        response = self.patch({"scheduled_date": None})
        self.assertEqual(response.status_code, 400)
        self.assertIn("scheduled_date", response.json()["details"])

    def test_past_date_is_rejected(self):
        response = self.patch({"scheduled_date": (self.today - timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"]["scheduled_date"],
            ["La fecha objetivo no puede ser anterior a hoy."],
        )

    def test_nonexistent_subtask_returns_standard_404(self):
        response = self.patch({"scheduled_date": self.today.isoformat()}, subtask_id=99999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.json()), {"error"})


class DailyOverloadConflictTests(TestCase):
    """US-07: conflicto cuando la carga del día destino supera el límite diario."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rosa@eventos.com", email="rosa@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.day_x = self.today + timedelta(days=2)
        self.event = Event.objects.create(
            user=self.user, name="Boda", event_date=self.today + timedelta(days=10)
        )
        self.subtask = LogisticSubtask.objects.create(
            event=self.event,
            name="Buscar proveedores",
            scheduled_date=self.today,
            estimated_hours="2.0",
        )

    def plan(self, day, hours, status="pending", event=None):
        return LogisticSubtask.objects.create(
            event=event or self.event,
            name="Planificada",
            scheduled_date=day,
            estimated_hours=hours,
            status=status,
        )

    def move(self, day, **extra):
        return self.client.patch(
            f"/api/subtasks/{self.subtask.id}/",
            {"scheduled_date": day.isoformat(), **extra},
            content_type="application/json",
        )

    def test_conflict_returns_409_with_date_hours_and_limit(self):
        self.plan(self.day_x, "3.0")
        self.plan(self.day_x, "2.0")
        response = self.move(self.day_x)
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"], "Quedarías con 7h de gestión planificadas (límite 6h).")
        details = body["details"]
        self.assertEqual(details["conflict"], "daily_overload")
        self.assertEqual(details["date"], self.day_x.isoformat())
        self.assertEqual(details["planned_hours"], 5.0)
        self.assertEqual(details["resulting_hours"], 7.0)
        self.assertEqual(details["limit_hours"], 6)
        self.assertEqual(
            [o["action"] for o in details["options"]], ["move", "reduce_hours", "postpone"]
        )

    def test_conflict_does_not_save(self):
        self.plan(self.day_x, "5.0")
        self.move(self.day_x)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.scheduled_date, self.today)

    def test_no_conflict_saves(self):
        self.plan(self.day_x, "3.0")
        self.assertEqual(self.move(self.day_x).status_code, 200)

    def test_reaching_exactly_the_limit_is_not_a_conflict(self):
        self.plan(self.day_x, "4.0")
        self.assertEqual(self.move(self.day_x).status_code, 200)

    def test_confirmed_overload_is_saved(self):
        self.plan(self.day_x, "5.0")
        response = self.move(self.day_x, confirm_overload=True)
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.scheduled_date, self.day_x)

    def test_done_and_postponed_subtasks_do_not_count(self):
        self.plan(self.day_x, "5.0", status="done")
        self.plan(self.day_x, "5.0", status="postponed")
        self.assertEqual(self.move(self.day_x).status_code, 200)

    def test_in_progress_subtasks_count(self):
        self.plan(self.day_x, "5.0", status="in_progress")
        self.assertEqual(self.move(self.day_x).status_code, 409)

    def test_load_includes_all_events_of_the_organizer(self):
        other_event = Event.objects.create(
            user=self.user, name="Cumpleaños", event_date=self.today + timedelta(days=10)
        )
        self.plan(self.day_x, "5.0", event=other_event)
        self.assertEqual(self.move(self.day_x).status_code, 409)

    def test_other_organizers_load_does_not_count(self):
        other = User.objects.create_user("otra", password="x")
        other_event = Event.objects.create(
            user=other, name="Ajeno", event_date=self.today + timedelta(days=10)
        )
        self.plan(self.day_x, "5.0", event=other_event)
        self.assertEqual(self.move(self.day_x).status_code, 200)

    def test_increasing_hours_on_same_day_detects_conflict(self):
        self.plan(self.today, "4.0")
        response = self.client.patch(
            f"/api/subtasks/{self.subtask.id}/",
            {"estimated_hours": 3},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["details"]["resulting_hours"], 7.0)

    def test_editing_other_fields_does_not_evaluate_conflict(self):
        self.plan(self.today, "6.0")  # el día ya estaba sobrecargado
        response = self.client.patch(
            f"/api/subtasks/{self.subtask.id}/",
            {
                "name": "Buscar proveedores de flores",
                "scheduled_date": self.today.isoformat(),
                "estimated_hours": "2.0",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_postponing_is_never_a_conflict(self):
        self.plan(self.day_x, "5.0")
        response = self.move(self.day_x, status="postponed")
        self.assertEqual(response.status_code, 200)

    def test_invalid_confirm_flag_is_rejected(self):
        response = self.move(self.day_x, confirm_overload="quizás")
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_overload", response.json()["details"])


class ResolveOverloadConflictTests(TestCase):
    """US-08: días sugeridos, recálculo al mover o reducir horas y validación de horas."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rosa@eventos.com", email="rosa@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.day_x = self.today + timedelta(days=2)
        self.event = Event.objects.create(
            user=self.user, name="Boda", event_date=self.today + timedelta(days=4)
        )
        self.subtask = LogisticSubtask.objects.create(
            event=self.event,
            name="Buscar proveedores",
            scheduled_date=self.day_x,
            estimated_hours="3.0",
        )

    def plan(self, day, hours):
        LogisticSubtask.objects.create(
            event=self.event, name="Planificada", scheduled_date=day, estimated_hours=hours
        )

    def patch(self, payload):
        return self.client.patch(
            f"/api/subtasks/{self.subtask.id}/", payload, content_type="application/json"
        )

    def test_suggested_dates_fit_within_limit_and_event(self):
        self.subtask.scheduled_date = self.today
        self.subtask.save()
        self.plan(self.day_x, "5.0")
        self.plan(self.today + timedelta(days=3), "4.0")  # no cabe: 4 + 3 > 6
        response = self.patch({"scheduled_date": self.day_x.isoformat()})
        self.assertEqual(response.status_code, 409)
        suggested = response.json()["details"]["suggested_dates"]
        self.assertNotIn(self.day_x.isoformat(), suggested)
        self.assertNotIn((self.today + timedelta(days=3)).isoformat(), suggested)
        self.assertEqual(
            suggested,
            sorted(
                [
                    (self.today + timedelta(days=1)).isoformat(),
                    (self.today + timedelta(days=4)).isoformat(),
                    self.today.isoformat(),
                ]
            ),
        )

    def test_moving_to_suggested_day_resolves_conflict(self):
        self.subtask.scheduled_date = self.today
        self.subtask.save()
        self.plan(self.day_x, "5.0")
        suggested = self.patch({"scheduled_date": self.day_x.isoformat()}).json()["details"][
            "suggested_dates"
        ]
        response = self.patch({"scheduled_date": suggested[0]})
        self.assertEqual(response.status_code, 200)

    def test_reducing_hours_resolves_conflict(self):
        self.subtask.status = "postponed"
        self.subtask.save()
        self.plan(self.day_x, "5.0")
        # Al reactivarla se detecta: 5 + 3 = 8 > 6
        self.assertEqual(self.patch({"status": "pending"}).status_code, 409)
        response = self.patch(
            {"status": "pending", "estimated_hours": 1, "resolution": "reduce_hours"}
        )
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.estimated_hours, Decimal("1.0"))

    def test_insufficient_reduction_keeps_conflict_with_new_figures(self):
        self.plan(self.day_x, "5.0")
        response = self.patch({"estimated_hours": 2, "resolution": "reduce_hours"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"], "Quedarías con 7h de gestión planificadas (límite 6h)."
        )
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.estimated_hours, Decimal("3.0"))

    def test_reduced_hours_must_be_less_than_current(self):
        for hours in (3, 4):
            response = self.patch({"estimated_hours": hours, "resolution": "reduce_hours"})
            self.assertEqual(response.status_code, 400)
            self.assertIn("menores que las estimadas actualmente (3h)",
                          response.json()["details"]["estimated_hours"][0])

    def test_reduced_hours_must_be_greater_than_zero(self):
        for hours in (0, -1):
            response = self.patch({"estimated_hours": hours, "resolution": "reduce_hours"})
            self.assertEqual(response.status_code, 400)
            self.assertIn("estimated_hours", response.json()["details"])
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.estimated_hours, Decimal("3.0"))

    def test_reduce_hours_requires_hours(self):
        response = self.patch({"resolution": "reduce_hours"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("estimated_hours", response.json()["details"])

    def test_unknown_resolution_is_rejected(self):
        response = self.patch({"resolution": "magia"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("resolution", response.json()["details"])


class DailyLimitSettingsTests(TestCase):
    """US-12: GET y PATCH /api/settings/daily-limit/ y su uso en la detección."""

    URL = "/api/settings/daily-limit/"

    def setUp(self):
        self.user = User.objects.create_user(
            "rosa@eventos.com", email="rosa@eventos.com", password="Secreta123"
        )
        self.client.force_login(self.user)

    def patch(self, payload):
        return self.client.patch(self.URL, payload, content_type="application/json")

    def test_default_limit_is_6(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"daily_hours_limit": 6})

    def test_update_valid_limit(self):
        response = self.patch({"daily_hours_limit": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"daily_hours_limit": 4})
        self.assertEqual(self.client.get(self.URL).json()["daily_hours_limit"], 4)

    def test_range_bounds_are_allowed(self):
        for value in (1, 16):
            self.assertEqual(self.patch({"daily_hours_limit": value}).status_code, 200)

    def test_out_of_range_values_are_rejected_with_range_message(self):
        for value in (0, 17, -3, 4.5, "abc"):
            response = self.patch({"daily_hours_limit": value})
            self.assertEqual(response.status_code, 400, value)
            body = response.json()
            self.assertIn("error", body)
            self.assertIn("entre 1 y 16", body["details"]["daily_hours_limit"][0])
        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_hours_limit, 6)

    def test_missing_value_is_rejected(self):
        response = self.patch({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"]["daily_hours_limit"], ["El límite diario es obligatorio."]
        )

    def test_limit_is_per_organizer(self):
        other = User.objects.create_user("b@eventos.com", email="b@eventos.com", password="x")
        other.daily_hours_limit = 4
        other.save()
        self.assertEqual(self.client.get(self.URL).json()["daily_hours_limit"], 6)
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.URL).json()["daily_hours_limit"], 4)

    def test_conflict_detection_uses_the_new_limit(self):
        today = timezone.localdate()
        event = Event.objects.create(
            user=self.user, name="Boda", event_date=today + timedelta(days=5)
        )
        LogisticSubtask.objects.create(
            event=event, name="Planificada", scheduled_date=today + timedelta(days=1),
            estimated_hours="3.0",
        )
        subtask = LogisticSubtask.objects.create(
            event=event, name="Mover", scheduled_date=today, estimated_hours="2.0"
        )
        move = lambda: self.client.patch(  # noqa: E731
            f"/api/subtasks/{subtask.id}/",
            {"scheduled_date": (today + timedelta(days=1)).isoformat()},
            content_type="application/json",
        )
        self.patch({"daily_hours_limit": 4})
        response = move()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"], "Quedarías con 5h de gestión planificadas (límite 4h)."
        )

class SubtaskExecutionAndPostponeTests(TestCase):
    """US-09 (PI-139, PI-140, PI-141): Actualizar status y note en PATCH /api/subtasks/:id/."""

    def setUp(self):
        self.user = User.objects.create_user("organizador", email="org@eventos.com", password="x")
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.event = Event.objects.create(user=self.user, name="Boda", event_date=self.today + timedelta(days=10))
        self.subtask = LogisticSubtask.objects.create(
            event=self.event,
            name="Catering",
            scheduled_date=self.today,
            status=LogisticSubtask.Status.PENDING,
            estimated_hours=Decimal("2.0"),
        )

    def patch(self, payload):
        return self.client.patch(
            f"/api/subtasks/{self.subtask.id}/",
            payload,
            content_type="application/json",
        )

    def test_mark_subtask_as_done(self):
        response = self.patch({"status": "done"})
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.status, LogisticSubtask.Status.DONE)

    def test_postpone_subtask_with_optional_note(self):
        note = "Esperando confirmación del proveedor de mantelería"
        response = self.patch({"status": "postponed", "note": note})
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.status, LogisticSubtask.Status.POSTPONED)
        self.assertEqual(self.subtask.note, note)

    def test_postpone_subtask_without_note_is_valid(self):
        response = self.patch({"status": "postponed"})
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.status, LogisticSubtask.Status.POSTPONED)

    def test_invalid_status_returns_400_with_allowed_choices(self):
        response = self.patch({"status": "finalizado_invalido"})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("status", body["details"])
        self.assertIn("Valores permitidos", body["details"]["status"][0])

    def test_note_can_be_cleared_or_empty(self):
        self.subtask.note = "Nota anterior"
        self.subtask.save()
        response = self.patch({"note": ""})
        self.assertEqual(response.status_code, 200)
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.note, "")

    def test_today_view_includes_note_for_subtasks(self):
        self.subtask.note = "Nota visible en hoy"
        self.subtask.save()
        res = self.client.get("/api/today/").json()
        all_tasks = res["overdue"] + res["due_today"] + res["upcoming"]
        task_in_today = next(t for t in all_tasks if t["id"] == self.subtask.id)
        self.assertEqual(task_in_today["note"], "Nota visible en hoy")


class EventProgressTests(TestCase):
    """US-10 (PI-151, PI-152, PI-153): Progreso de preparación del evento."""

    def setUp(self):
        self.user = User.objects.create_user("organizador", email="org@eventos.com", password="x")
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.event = Event.objects.create(
            user=self.user, name="Boda de Prueba", event_date=self.today + timedelta(days=15)
        )

    def test_event_without_subtasks_has_zero_progress(self):
        response = self.client.get(f"/api/progress/?event={self.event.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["executed"], 0)
        self.assertEqual(data["completed"], 0)
        self.assertEqual(data["percentage"], 0.0)

    def test_progress_calculation_counts_only_done_as_executed(self):
        # 1 done, 1 in_progress, 1 pending, 1 postponed -> total: 4, executed: 1, 25.0%
        LogisticSubtask.objects.create(event=self.event, name="T1", scheduled_date=self.today, status="done")
        LogisticSubtask.objects.create(event=self.event, name="T2", scheduled_date=self.today, status="in_progress")
        LogisticSubtask.objects.create(event=self.event, name="T3", scheduled_date=self.today, status="pending")
        LogisticSubtask.objects.create(event=self.event, name="T4", scheduled_date=self.today, status="postponed")

        response = self.client.get(f"/api/progress/?event={self.event.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["executed"], 1)
        self.assertEqual(data["completed"], 1)
        self.assertEqual(data["percentage"], 25.0)

    def test_progress_list_returns_all_organizer_events(self):
        other = Event.objects.create(
            user=self.user, name="Cumpleaños", event_date=self.today + timedelta(days=20)
        )
        LogisticSubtask.objects.create(event=other, name="T1", scheduled_date=self.today, status="done")

        response = self.client.get("/api/progress/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        event_names = [e["event_name"] for e in data]
        self.assertIn("Boda de Prueba", event_names)
        self.assertIn("Cumpleaños", event_names)

    def test_event_detail_includes_calculated_progress(self):
        LogisticSubtask.objects.create(event=self.event, name="T1", scheduled_date=self.today, status="done")
        LogisticSubtask.objects.create(event=self.event, name="T2", scheduled_date=self.today, status="pending")

        response = self.client.get(f"/api/events/{self.event.id}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("progress", body)
        self.assertEqual(body["progress"]["total"], 2)
        self.assertEqual(body["progress"]["executed"], 1)
        self.assertEqual(body["progress"]["percentage"], 50.0)

    def test_cannot_access_foreign_event_progress(self):
        foreign_user = User.objects.create_user("ajeno", password="x")
        foreign_event = Event.objects.create(
            user=foreign_user, name="Ajeno", event_date=self.today + timedelta(days=5)
        )
        response = self.client.get(f"/api/progress/?event={foreign_event.id}")
        self.assertEqual(response.status_code, 404)