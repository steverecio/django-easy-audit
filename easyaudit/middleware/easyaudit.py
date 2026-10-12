# makes easy-audit thread-safe
import contextlib
from typing import Callable

from asgiref.local import Local
from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.http.request import HttpRequest
from django.http.response import HttpResponse

from easyaudit.request_auth import adapters_require_response
from easyaudit.utils import should_propagate_exceptions


class MockRequest:
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)


_thread_locals = Local()


def get_current_request():
    return getattr(_thread_locals, "request", None)


def get_current_user():
    request = get_current_request()
    if request:
        return getattr(request, "user", None)
    return None


def set_current_user(user):
    try:
        _thread_locals.request.user = user
    except AttributeError:
        request = MockRequest(user=user)
        _thread_locals.request = request


def clear_request():
    with contextlib.suppress(AttributeError):
        del _thread_locals.request


def log_request(request):
    """Log the request, for auth adapters that need the view to have run."""
    # Imported here: easyaudit.settings needs the app registry to be ready.
    from easyaudit.settings import WATCH_REQUEST_EVENTS
    from easyaudit.signals.request_signals import log_request_after_response

    if not WATCH_REQUEST_EVENTS:
        return

    try:
        log_request_after_response(request)
    except Exception:
        if should_propagate_exceptions():
            raise


class EasyAuditMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if iscoroutinefunction(self):
            return self.__acall__(request)

        _thread_locals.request = request
        response = self.get_response(request)

        with contextlib.suppress(AttributeError):
            del _thread_locals.request

        if adapters_require_response():
            log_request(request)

        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        _thread_locals.request = request

        response = await self.get_response(request)

        with contextlib.suppress(AttributeError):
            del _thread_locals.request

        if adapters_require_response():
            await sync_to_async(log_request)(request)

        return response
