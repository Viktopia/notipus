"""
URL configuration for django_notipus project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from ninja import NinjaAPI
from webhooks.webhook_router import webhook_router

ninja_api = NinjaAPI(
    title="Notipus API",
    version="1.0",
    description="API for Slack authentication and integrations management",
)

# Add router only if not already attached (prevents test failures)
if not hasattr(webhook_router, 'api') or webhook_router.api is None:
    ninja_api.add_router("/", webhook_router, tags=["Webhooks"])

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("", ninja_api.urls),
]
