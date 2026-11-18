from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from beobenere.security import get_client_ip

PASSWORD = "mot-de-passe-test-solide"


class ClientIpTests(TestCase):
    """L'adresse IP du visiteur : derrière Nginx, c'est X-Real-IP qui la porte, mais seulement si la requête vient de la machine elle-même."""

    def ip(self, **meta):
        return get_client_ip(RequestFactory().get("/", **meta))

    def test_uses_remote_addr_by_default(self):
        self.assertEqual(self.ip(REMOTE_ADDR="203.0.113.7"), "203.0.113.7")

    def test_uses_x_real_ip_when_request_comes_from_local_proxy(self):
        self.assertEqual(self.ip(REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="198.51.100.5"), "198.51.100.5")

    def test_ignores_x_real_ip_when_request_does_not_come_from_local_proxy(self):
        # Un visiteur qui écrirait lui-même cet en-tête ne doit pas pouvoir choisir son adresse.
        self.assertEqual(self.ip(REMOTE_ADDR="203.0.113.7", HTTP_X_REAL_IP="198.51.100.9"), "203.0.113.7")

    def test_ignores_invalid_x_real_ip(self):
        self.assertEqual(self.ip(REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="pas-une-adresse"), "127.0.0.1")

    def test_works_with_ipv6_local_proxy(self):
        self.assertEqual(self.ip(REMOTE_ADDR="::1", HTTP_X_REAL_IP="198.51.100.5"), "198.51.100.5")


# Hachage rapide : ces tests font des dizaines de connexions, et le hachage réel est volontairement lent.
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminLoginLockoutTests(TestCase):
    """Après 5 mots de passe faux, l'adresse est bloquée un moment, même avec le bon mot de passe."""

    def setUp(self):
        get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password=PASSWORD)
        self.login_url = reverse("admin:login")

    def attempt(self, password, ip="203.0.113.7", **meta):
        return self.client.post(self.login_url, {"username": "admin", "password": password}, REMOTE_ADDR=ip, **meta)

    def fail(self, times, **kwargs):
        for _ in range(times):
            self.attempt("mauvais-mot-de-passe", **kwargs)

    def test_correct_password_works_after_a_few_failures(self):
        self.fail(4)
        self.assertEqual(self.attempt(PASSWORD).status_code, 302)

    def test_address_is_locked_after_five_failures(self):
        self.fail(5)
        response = self.attempt(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Trop de tentatives de connexion", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_another_address_is_not_locked(self):
        self.fail(5, ip="203.0.113.7")
        self.assertEqual(self.attempt(PASSWORD, ip="203.0.113.8").status_code, 302)

    def test_successful_login_resets_the_counter(self):
        self.fail(4)
        self.assertEqual(self.attempt(PASSWORD).status_code, 302)
        self.client.logout()
        self.fail(4)
        self.assertEqual(self.attempt(PASSWORD).status_code, 302)

    def test_lockout_follows_the_real_address_behind_the_proxy(self):
        # Toutes les requêtes arrivent de 127.0.0.1 (Nginx) ; seule X-Real-IP distingue les visiteurs.
        self.fail(5, ip="127.0.0.1", HTTP_X_REAL_IP="198.51.100.5")
        self.assertEqual(self.attempt(PASSWORD, ip="127.0.0.1", HTTP_X_REAL_IP="198.51.100.5").status_code, 429)
        self.assertEqual(self.attempt(PASSWORD, ip="127.0.0.1", HTTP_X_REAL_IP="198.51.100.6").status_code, 302)
