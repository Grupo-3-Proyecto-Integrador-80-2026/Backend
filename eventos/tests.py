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
