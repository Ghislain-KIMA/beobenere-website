from django import forms
from django.contrib import admin

from .models import Company


class CompanyAdminForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = "__all__"
        widgets = {
            "phone": forms.TextInput(attrs={"class": "phone-input"}),
            "whatsapp": forms.TextInput(attrs={"class": "phone-input"}),
        }


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    form = CompanyAdminForm

    def has_add_permission(self, request):
        # Le site n'a qu'une seule entreprise : on ne peut en créer une que si la table est vide.
        return not Company.objects.exists()

    class Media:
        css = {
            "all": ("vendor/intl-tel-input/css/intlTelInput.min.css",)
        }
        js = (
            "vendor/intl-tel-input/js/intlTelInput.min.js",
            "js/phone-widget.js",
        )
