"""S2C App URLs"""
from django.urls import path
from . import views

urlpatterns = [
    # Health
    path('health/', views.health_check, name='health'),

    # Files
    path('files/', views.list_files, name='file-list'),
    path('files/create/', views.create_file, name='file-create'),
    path('files/delete/', views.delete_files, name='file-delete'),

    # Ride (Auto Rickshaw example!)
    path('ride/book/', views.book_ride, name='ride-book'),

    # Generic S2C
    path('process/', views.process_with_elicitation, name='process'),

    # Logs
    path('logs/', views.elicitation_logs, name='elicitation-logs'),
]
