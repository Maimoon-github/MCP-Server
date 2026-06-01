"""Stateless App Models — No session fields"""
from django.db import models

class Product(models.Model):
    """Example resource — any server can handle requests for it."""
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'products'

    def __str__(self):
        return f"{self.name} (${self.price})"

class Order(models.Model):
    """Order contains ALL context needed — no server remembers state."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    customer_email = models.EmailField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orders'

    def __str__(self):
        return f"Order #{self.id} — {self.customer_email}"
