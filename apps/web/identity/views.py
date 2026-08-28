"""CSRF-protected, session-only browser authentication."""

from __future__ import annotations

from django.contrib.auth import login as session_login
from django.contrib.auth import logout as session_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.web.identity.throttling import LoginThrottle, LoginThrottleUnavailableError


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("api-me")

    form = AuthenticationForm(request=request, data=request.POST or None)
    status = 200
    if request.method == "POST":
        username = request.POST.get("username", "")[:150]
        throttle = LoginThrottle()
        try:
            if throttle.is_blocked(request, username):
                form.add_error(None, "Sign-in is temporarily unavailable. Try again later.")
                status = 429
            elif form.is_valid():
                throttle.clear(request, username)
                session_login(request, form.get_user())
                return redirect("api-me")
            else:
                throttle.record_failure(request, username)
        except LoginThrottleUnavailableError:
            form.add_error(None, "Sign-in is temporarily unavailable. Try again later.")
            status = 503
    return render(request, "identity/login.html", {"form": form}, status=status)


@login_required
@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    session_logout(request)
    return redirect("login")
