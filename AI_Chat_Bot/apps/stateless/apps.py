from django.apps import AppConfig


class StatelessConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.stateless'
    verbose_name = 'Stateless MCP Server'