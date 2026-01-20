"""Custom error handlers for the application.

These handlers render custom error templates to provide a better user experience
and avoid issues with Django's default debug error templates.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def custom_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Render custom 404 page.

    Args:
        request: The HTTP request that resulted in 404.
        exception: The exception that triggered the 404.

    Returns:
        HttpResponse with 404 status code.
    """
    return render(request, "404.html.j2", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    """Render custom 500 page.

    Args:
        request: The HTTP request that resulted in 500.

    Returns:
        HttpResponse with 500 status code.
    """
    return render(request, "500.html.j2", status=500)
