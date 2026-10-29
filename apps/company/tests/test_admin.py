from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from company.admin import CompanyAdmin
from company.models import Company


class CompanyAdminAddPermissionTests(TestCase):
    """Le site n'a qu'une seule entreprise : l'admin ne doit pas permettre d'en créer une deuxième."""

    def setUp(self):
        self.model_admin = CompanyAdmin(Company, admin.site)
        self.superuser = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="mot-de-passe-test"
        )
        self.request = RequestFactory().get("/admin/company/company/")
        self.request.user = self.superuser

    def create_company(self):
        return Company.objects.create(
            name="BeoBenere",
            email="beobenere.business@gmail.com",
            phone="+22672750096",
        )

    def test_can_add_when_no_company_exists(self):
        self.assertTrue(self.model_admin.has_add_permission(self.request))

    def test_cannot_add_when_a_company_exists(self):
        self.create_company()
        self.assertFalse(self.model_admin.has_add_permission(self.request))

    def test_add_page_is_forbidden_when_a_company_exists(self):
        self.create_company()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:company_company_add"))
        self.assertEqual(response.status_code, 403)

    def test_add_page_opens_when_no_company_exists(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:company_company_add"))
        self.assertEqual(response.status_code, 200)

    def test_existing_company_can_still_be_edited(self):
        company = self.create_company()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:company_company_change", args=[company.pk]))
        self.assertEqual(response.status_code, 200)
