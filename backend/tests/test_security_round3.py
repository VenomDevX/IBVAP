"""Security round 3: API bind address and critical-webhook URL validation."""

import pytest


def test_backend_listens_on_localhost_unless_configured(monkeypatch):
    import main

    monkeypatch.delenv("IBVAP_HOST", raising=False)
    assert main.default_host() == "127.0.0.1"

    monkeypatch.setenv("IBVAP_HOST", "0.0.0.0")
    assert main.default_host() == "0.0.0.0"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/hook",
        "gopher://example.com/",
        "http://example.com/hook",  # alert data in clear text over the network
        "https://",
        "not a url",
    ],
)
def test_critical_webhook_rejects_unsafe_urls(monkeypatch, url):
    from src.alerts.notifiers import NotificationManager

    monkeypatch.setenv("IBVAP_CRITICAL_WEBHOOK_URL", url)
    assert NotificationManager().webhook_url == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://hooks.example.com/ibvap",
        "http://127.0.0.1:9000/hook",
        "http://localhost/hook",
    ],
)
def test_critical_webhook_accepts_https_and_loopback_http(monkeypatch, url):
    from src.alerts.notifiers import NotificationManager

    monkeypatch.setenv("IBVAP_CRITICAL_WEBHOOK_URL", url)
    assert NotificationManager().webhook_url == url
