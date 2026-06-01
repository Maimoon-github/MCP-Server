"""Stateless App URLs"""
from django.urls import path
from . import views

urlpatterns = [
    # Health check (no auth)
    path('health/', views.health_check, name='health'),

    # Products
    path('products/', views.product_list, name='product-list'),
    path('products/create/', views.product_create, name='product-create'),
    path('products/<int:pk>/', views.product_detail, name='product-detail'),

    # Orders
    path('orders/', views.order_list, name='order-list'),
    path('orders/create/', views.order_create, name='order-create'),
]
