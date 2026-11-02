from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from contact.models import ContactMessage
from contact.notifications import send_pending_notifications


@override_settings(
    CONTACT_NOTIFICATION_EMAIL="contact@example.com",
    SITE_URL="https://beobenere.test",
)
class SendPendingNotificationsTests(TestCase):
    def create_message(self, **overrides):
        data = {
            "full_name": "Awa Ouédraogo",
            "email": "awa@example.com",
            "message": "Bonjour, j'aimerais un rendez-vous.",
        }
        data.update(overrides)
        return ContactMessage.objects.create(**data)

    def test_pending_message_is_notified_and_marked(self):
        contact_message = self.create_message()

        sent, failed = send_pending_notifications()

        self.assertEqual((sent, failed), (1, 0))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["contact@example.com"])
        self.assertIn("Nouveau message de contact", email.subject)
        self.assertIn("Awa Ouédraogo", email.subject)
        self.assertIn(
            f"https://beobenere.test/admin/contact/contactmessage/{contact_message.pk}/change/",
            email.body,
        )
        contact_message.refresh_from_db()
        self.assertIsNotNone(contact_message.notified_at)

    def test_already_notified_message_is_not_sent_again(self):
        self.create_message()
        send_pending_notifications()

        sent, failed = send_pending_notifications()

        self.assertEqual((sent, failed), (0, 0))
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_send_keeps_message_pending(self):
        contact_message = self.create_message()

        with mock.patch("contact.notifications.send_mail", side_effect=Exception("SMTP indisponible")):
            with self.assertLogs("contact.notifications", level="ERROR"):
                sent, failed = send_pending_notifications()

        self.assertEqual((sent, failed), (0, 1))
        contact_message.refresh_from_db()
        self.assertIsNone(contact_message.notified_at)

    def test_email_body_contains_the_visitor_message(self):
        self.create_message(message="Bonjour, j'aimerais un rendez-vous mardi.")

        send_pending_notifications()

        self.assertIn("Bonjour, j'aimerais un rendez-vous mardi.", mail.outbox[0].body)

    def test_all_pending_messages_are_notified(self):
        first = self.create_message(full_name="Premier Visiteur", email="premier@example.com")
        second = self.create_message(full_name="Second Visiteur", email="second@example.com")

        sent, failed = send_pending_notifications()

        self.assertEqual((sent, failed), (2, 0))
        self.assertEqual(len(mail.outbox), 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.notified_at)
        self.assertIsNotNone(second.notified_at)

    def test_one_failure_does_not_block_the_other_messages(self):
        failing = self.create_message(full_name="Premier Visiteur", email="premier@example.com")
        working = self.create_message(full_name="Second Visiteur", email="second@example.com")

        def fail_for_first_visitor(subject, *args, **kwargs):
            if "Premier Visiteur" in subject:
                raise Exception("SMTP indisponible")

        with mock.patch("contact.notifications.send_mail", side_effect=fail_for_first_visitor) as send_mail:
            with self.assertLogs("contact.notifications", level="ERROR"):
                sent, failed = send_pending_notifications()

        self.assertEqual((sent, failed), (1, 1))
        self.assertEqual(send_mail.call_count, 2)
        failing.refresh_from_db()
        working.refresh_from_db()
        self.assertIsNone(failing.notified_at)
        self.assertIsNotNone(working.notified_at)

    def test_command_reports_sent_notifications(self):
        self.create_message()
        out = StringIO()

        call_command("send_contact_notifications", stdout=out)

        self.assertIn("1 notification(s) envoyée(s)", out.getvalue())

    def test_command_is_silent_when_nothing_pending(self):
        out = StringIO()

        call_command("send_contact_notifications", stdout=out)

        self.assertEqual(out.getvalue(), "")