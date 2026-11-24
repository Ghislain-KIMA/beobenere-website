from django.test import TestCase


class LocationWordingTests(TestCase):
    """BeoBenere est basée à Tenkodogo et sert aussi à distance : aucune page ne doit annoncer une autre ville."""

    PAGES = ["/", "/a-propos/", "/mentions-legales/", "/services/", "/devis/", "/contact/"]

    def test_pages_do_not_claim_ouagadougou(self):
        for url in self.PAGES:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "Ouagadougou")

    def test_legal_notice_gives_the_real_location(self):
        self.assertContains(self.client.get("/mentions-legales/"), "à Tenkodogo (Burkina Faso)")

    def test_default_meta_description_and_share_title_name_the_real_location(self):
        response = self.client.get("/")
        self.assertContains(response, "services informatiques à Tenkodogo")
        self.assertContains(response, 'property="og:title" content="BeoBenere — Services informatiques à Tenkodogo')

    def test_contact_page_does_not_promise_opening_days_in_its_description(self):
        self.assertNotContains(self.client.get("/contact/"), "du lundi au vendredi")
