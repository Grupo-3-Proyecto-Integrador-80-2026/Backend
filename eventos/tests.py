from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Event, LogisticSubtask, User


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
