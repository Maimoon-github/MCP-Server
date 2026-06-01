from django.apps import AppConfig


class S2CConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.s2c'
    verbose_name = 'Stateless Server-to-Client Elicitation (S2C)'
