import importlib
import os
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import clear_url_caches, reverse

from company.models import Company


class HomepageViewTest(TestCase):
    def test_page_loads(self):
        response = self.client.get(reverse("homepage:homepage"))
        self.assertEqual(response.status_code, 200)

    def test_shows_company_name_when_company_exists(self):
        Company.objects.create(
            name="BeoBenere",
            email="beobenere.business@gmail.com",
            phone="+22672750096",
        )
        response = self.client.get(reverse("homepage:homepage"))
        self.assertContains(response, "BeoBenere")

    def test_does_not_crash_when_no_company_exists(self):
        """Company.objects.first() peut renvoyer None, la page ne doit pas planter pour autant."""
        response = self.client.get(reverse("homepage:homepage"))
        self.assertEqual(response.status_code, 200)

    def test_about_page_loads(self):
        response = self.client.get(reverse("homepage:about"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homepage/about.html")

    def test_about_page_shows_company_practical_info(self):
        Company.objects.create(
            name="BeoBenere",
            email="contact@example.com",
            phone="+22670000000",
            service_area="Ouagadougou et environs",
            business_hours="Lundi – Vendredi, 8h – 18h",
        )

        response = self.client.get(reverse("homepage:about"))

        self.assertContains(response, "Ouagadougou et environs")
        self.assertContains(response, "Lundi – Vendredi, 8h – 18h")

    def test_about_page_hides_practical_section_without_company(self):
        response = self.client.get(reverse("homepage:about"))
        self.assertNotContains(response, "Où et quand")

    def test_legal_page_loads(self):
        response = self.client.get(reverse("homepage:legal"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homepage/legal.html")

    def test_legal_page_shows_company_contact(self):
        """L'éditeur du site et son moyen de contact viennent de la fiche Company."""
        Company.objects.create(
            name="BeoBenere",
            email="contact@example.com",
            phone="+22670000000",
        )
        response = self.client.get(reverse("homepage:legal"))
        self.assertContains(response, "contact@example.com")

    def test_legal_page_without_company_does_not_crash(self):
        """Comme le reste du site, la page doit s'afficher même sans fiche Company."""
        response = self.client.get(reverse("homepage:legal"))
        self.assertEqual(response.status_code, 200)


class AllowedHostsSettingTest(SimpleTestCase):
    """ALLOWED_HOSTS est lu dans le .env : les espaces et les valeurs vides ne doivent pas casser la liste."""

    def _read_allowed_hosts(self, value):
        """Relit settings.py avec une valeur donnée pour ALLOWED_HOSTS (None = variable absente).

        load_dotenv est neutralisé pour que le vrai fichier .env de la machine
        ne vienne pas remettre une valeur dans l'environnement du test.
        """
        settings_module = importlib.import_module("beobenere.settings")
        self.addCleanup(importlib.reload, settings_module)
        with patch.dict(os.environ), patch("dotenv.load_dotenv"):
            if value is None:
                os.environ.pop("ALLOWED_HOSTS", None)
            else:
                os.environ["ALLOWED_HOSTS"] = value
            return importlib.reload(settings_module).ALLOWED_HOSTS

    def test_spaces_around_hosts_are_removed(self):
        hosts = self._read_allowed_hosts("beobenere.com, www.beobenere.com")
        self.assertEqual(hosts, ["beobenere.com", "www.beobenere.com"])

    def test_empty_value_gives_empty_list(self):
        self.assertEqual(self._read_allowed_hosts(""), [])

    def test_missing_variable_gives_empty_list(self):
        self.assertEqual(self._read_allowed_hosts(None), [])

    def test_trailing_comma_is_ignored(self):
        self.assertEqual(self._read_allowed_hosts("beobenere.com,"), ["beobenere.com"])


class AdminUrlSettingTest(SimpleTestCase):
    """ADMIN_URL permet de déplacer l'admin hors de /admin/, adresse que tous les robots essaient."""

    def _read_admin_url(self, value):
        """Relit settings.py avec une valeur donnée pour ADMIN_URL (None = variable absente)."""
        settings_module = importlib.import_module("beobenere.settings")
        self.addCleanup(importlib.reload, settings_module)
        with patch.dict(os.environ), patch("dotenv.load_dotenv"):
            if value is None:
                os.environ.pop("ADMIN_URL", None)
            else:
                os.environ["ADMIN_URL"] = value
            return importlib.reload(settings_module).ADMIN_URL

    def test_default_is_admin(self):
        self.assertEqual(self._read_admin_url(None), "admin/")

    def test_empty_value_falls_back_to_admin(self):
        self.assertEqual(self._read_admin_url(""), "admin/")

    def test_custom_value_gets_a_trailing_slash(self):
        self.assertEqual(self._read_admin_url("gestion-beobenere"), "gestion-beobenere/")

    def test_slashes_and_spaces_are_cleaned(self):
        self.assertEqual(self._read_admin_url(" /gestion-beobenere/ "), "gestion-beobenere/")


class AdminUrlRoutingTest(TestCase):
    """L'adresse de l'admin suit ADMIN_URL, et l'ancienne adresse n'existe plus."""

    def _reload_urls(self):
        importlib.reload(importlib.import_module("beobenere.urls"))
        clear_url_caches()

    def test_admin_moves_to_the_configured_address(self):
        self.addCleanup(self._reload_urls)
        with override_settings(ADMIN_URL="gestion-test/"):
            self._reload_urls()
            self.assertEqual(reverse("admin:index"), "/gestion-test/")
            self.assertEqual(self.client.get("/gestion-test/login/").status_code, 200)
            self.assertEqual(self.client.get("/admin/login/").status_code, 404)

    def test_admin_is_served_on_admin_when_configured_so(self):
        self.addCleanup(self._reload_urls)
        with override_settings(ADMIN_URL="admin/"):
            self._reload_urls()
            self.assertEqual(reverse("admin:index"), "/admin/")
            self.assertEqual(self.client.get("/admin/login/").status_code, 200)
