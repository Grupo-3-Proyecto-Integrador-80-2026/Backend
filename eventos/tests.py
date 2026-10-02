from datetime import timedelta

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