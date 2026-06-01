"""
Stateless API Views — Session Ki Jhanjhat Khatam!

Principles:
- Har request apne aap mein poori hai.
- Koi session ID nahi. Koi "state" nahi.
- API Key har request mein aati hai.
- Load balancer seedha round-robin kar sakta hai — koi server handle kar sakta hai.
"""
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Product, Order
from .auth import APIKeyAuthentication

# ==========================
# PRODUCT ENDPOINTS
# ==========================

@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def product_list(request):
    """GET /api/products/ — Sab products list. No session needed."""
    products = Product.objects.all().values('id', 'name', 'price', 'stock')
    return Response({
        "status": "ok",
        "count": len(products),
        "data": list(products),
        "server_note": "Yeh request kisi bhi server ne handle ki — stateless!"
    })

@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def product_detail(request, pk):
    """GET /api/products/<id>/ — Ek product. Self-contained."""
    product = get_object_or_404(Product, pk=pk)
    return Response({
        "status": "ok",
        "data": {
            "id": product.id,
            "name": product.name,
            "price": str(product.price),
            "stock": product.stock,
        }
    })

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def product_create(request):
    """POST /api/products/ — Naya product. Data request mein poora."""
    data = request.data
    name = data.get('name')
    price = data.get('price')
    stock = data.get('stock', 0)

    if not name or price is None:
        return Response(
            {"error": "name aur price chahiye. Har request mein poora context do."},
            status=status.HTTP_400_BAD_REQUEST
        )

    product = Product.objects.create(name=name, price=price, stock=stock)
    return Response({
        "status": "created",
        "data": {
            "id": product.id,
            "name": product.name,
            "price": str(product.price),
            "stock": product.stock,
        }
    }, status=status.HTTP_201_CREATED)

# ==========================
# ORDER ENDPOINTS — "Order mein sab details, koi delivery boy yaad nahi rakhta"
# ==========================

@api_view(['POST'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def order_create(request):
    """
    POST /api/orders/ — Place order.
    Request mein sab kuch hona chahiye:
    - product_id
    - quantity
    - customer_email

    Server kuch "yaad" nahi rakhta. Har request fresh.
    """
    data = request.data
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    customer_email = data.get('customer_email')

    if not all([product_id, quantity, customer_email]):
        return Response(
            {"error": "product_id, quantity, customer_email — teeno chahiye!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    product = get_object_or_404(Product, pk=product_id)

    if product.stock < quantity:
        return Response(
            {"error": f"Stock nahi hai. Available: {product.stock}, Requested: {quantity}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    total = float(product.price) * int(quantity)

    order = Order.objects.create(
        product=product,
        quantity=quantity,
        customer_email=customer_email,
        total_amount=total
    )

    # Stock kam karo (idempotent if same request comes again with idempotency key)
    product.stock -= int(quantity)
    product.save()

    return Response({
        "status": "order_placed",
        "message": "Order mein sab details thi, server ne bina yaad rakhe process kar diya!",
        "data": {
            "order_id": order.id,
            "product": product.name,
            "quantity": quantity,
            "total": str(total),
            "customer_email": customer_email,
        }
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@authentication_classes([APIKeyAuthentication])
@permission_classes([IsAuthenticated])
def order_list(request):
    """GET /api/orders/ — Sab orders."""
    orders = Order.objects.select_related('product').all().values(
        'id', 'product__name', 'quantity', 'customer_email', 'total_amount', 'created_at'
    )
    return Response({
        "status": "ok",
        "count": len(orders),
        "data": list(orders),
    })

# ==========================
# HEALTH CHECK — Load Balancer ke liye
# ==========================

@api_view(['GET'])
def health_check(request):
    """GET /api/health/ — No auth needed. Load balancer check karega."""
    return Response({
        "status": "healthy",
        "mode": "stateless",
        "session": "nahi_hai",
        "message": "Koi bhi server request handle kar sakta hai. Round-robin chalega!"
    })
