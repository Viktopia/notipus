from django.urls import path
from . import views

urlpatterns = [
    path("webhook/shopify/", views.shopify_webhook, name="shopify_webhook"),
    path("webhook/chargify/", views.chargify_webhook, name="chargify_webhook"),
    path("health/", views.health_check, name="health_check"),
]
