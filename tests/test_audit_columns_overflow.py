"""A client-supplied value longer than its column must not lose the audit row.

The path, the method, X-Forwarded-For and a failed login's username all come from
the client. A database that enforces varchar lengths (Postgres, MySQL) rejects an
over-long value, and the row is lost. When an adapter needs the response, the
request row is written after the view, so the request does its work unaudited.
SQLite stores the long value, so these assert on what was stored as well as on
whether a row exists.
"""

import logging

import pytest
from django.test import RequestFactory
from django.urls import reverse

from easyaudit import utils
from easyaudit.middleware import easyaudit as middleware
from easyaudit.models import LoginEvent, RequestEvent
from easyaudit.signals import auth_signals, request_signals
from tests.test_app.models import Model

# A forged left end plus the entries the proxies appended: 66 characters.
LONG_CHAIN = "203.0.113.200, 198.51.100.17, 198.51.100.18, 10.0.1.23, 10.0.2.44"
# What fits in varchar(50): whole entries dropped from the left.
FITTED_CHAIN = "198.51.100.17, 198.51.100.18, 10.0.1.23, 10.0.2.44"
SHORT_CHAIN = "203.0.113.5, 10.0.1.23"


@pytest.fixture
def forwarded_for(monkeypatch):
    # Read once at import, so settings cannot reach it.
    for module in (request_signals, auth_signals):
        monkeypatch.setattr(module, "REMOTE_ADDR_HEADER", "HTTP_X_FORWARDED_FOR")


@pytest.fixture
def after_response(settings):
    """Log the request after the view, as a deployment with a token adapter does."""
    settings.DJANGO_EASY_AUDIT_REQUEST_AUTH_ADAPTERS = [
        "easyaudit.request_auth.RequestAuthAdapter",
        "easyaudit.request_auth.SessionAuthAdapter",
    ]
    settings.DJANGO_EASY_AUDIT_PROPAGATE_EXCEPTIONS = False


class TestFitForwardedChain:
    def fit(self, value):
        return utils.fit_forwarded_chain(RequestEvent, "remote_ip", value)

    def test_a_chain_that_fits_is_unchanged(self):
        assert self.fit(SHORT_CHAIN) == SHORT_CHAIN

    def test_entries_are_dropped_from_the_client_end(self):
        assert self.fit(LONG_CHAIN) == FITTED_CHAIN

    def test_one_overlong_entry_keeps_its_end(self):
        value = "x" * 60

        assert self.fit(value) == "x" * 50

    def test_none_is_unchanged(self):
        assert self.fit(None) is None


@pytest.mark.django_db
@pytest.mark.usefixtures("forwarded_for")
class TestRequestEventOverflow:
    @pytest.fixture(params=["before_view", "after_view"])
    def timing(self, request):
        if request.param == "after_view":
            request.getfixturevalue("after_response")
        return request.param

    def test_long_forwarded_chain_is_fitted(self, timing, client):
        resp = client.get(reverse("test_app:create-obj"), HTTP_X_FORWARDED_FOR=LONG_CHAIN)

        assert resp.status_code == 200
        assert Model.objects.count() == 1
        assert RequestEvent.objects.get().remote_ip == FITTED_CHAIN

    def test_short_forwarded_chain_is_stored_whole(self, timing, client):
        client.get(reverse("test_app:index"), HTTP_X_FORWARDED_FOR=SHORT_CHAIN)

        assert RequestEvent.objects.get().remote_ip == SHORT_CHAIN

    def test_missing_forwarded_header_is_stored_empty(self, timing, client):
        resp = client.get(reverse("test_app:create-obj"))

        assert resp.status_code == 200
        assert RequestEvent.objects.get().remote_ip == ""

    def test_long_path_is_cut_to_the_column(self, timing, client):
        path = reverse("test_app:index") + "x" * 300

        resp = client.get(path, HTTP_X_FORWARDED_FOR=SHORT_CHAIN)

        assert resp.status_code == 200
        assert RequestEvent.objects.get().url == path[:254]

    def test_long_method_is_cut_to_the_column(self, timing, client):
        client.generic(
            "X" * 30, reverse("test_app:index"), HTTP_X_FORWARDED_FOR=SHORT_CHAIN
        )

        assert RequestEvent.objects.get().method == "X" * 20


@pytest.mark.django_db
@pytest.mark.usefixtures("after_response")
class TestFailedRequestWrite:
    def test_a_failed_write_is_logged(self, client, caplog, monkeypatch):
        def fail(request_info):
            raise RuntimeError("boom")

        monkeypatch.setattr(request_signals.audit_logger, "request", fail)

        with caplog.at_level(logging.ERROR, logger=middleware.__name__):
            resp = client.get(reverse("test_app:index"))

        assert resp.status_code == 200
        assert "could not log a request" in caplog.text


@pytest.mark.django_db
@pytest.mark.usefixtures("forwarded_for")
class TestLoginEventOverflow:
    @pytest.fixture
    def request_with_long_chain(self):
        return RequestFactory().get("/", HTTP_X_FORWARDED_FOR=LONG_CHAIN)

    def test_login_with_long_forwarded_chain_is_recorded(
        self, user, request_with_long_chain
    ):
        auth_signals.user_logged_in(None, request=request_with_long_chain, user=user)

        assert LoginEvent.objects.get(login_type=LoginEvent.LOGIN).remote_ip == FITTED_CHAIN

    def test_failed_login_with_long_username_is_recorded(self, request_with_long_chain):
        middleware._thread_locals.request = request_with_long_chain
        try:
            auth_signals.user_login_failed(None, credentials={"username": "u" * 300})
        finally:
            middleware.clear_request()

        event = LoginEvent.objects.get(login_type=LoginEvent.FAILED)
        assert event.username == "u" * 255
        assert event.remote_ip == FITTED_CHAIN

    def test_failed_login_outside_a_request_is_recorded(self):
        middleware.clear_request()

        auth_signals.user_login_failed(None, credentials={"username": "joe"})

        assert LoginEvent.objects.get(login_type=LoginEvent.FAILED).remote_ip == ""
