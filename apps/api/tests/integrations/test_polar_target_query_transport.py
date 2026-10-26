"""Real Polar HTTP client, synthetic responses; no database or provider access."""

import asyncio
from datetime import date

import httpx
import pytest

from app.integrations.polar.client import PolarAPIError, PolarClient


@pytest.fixture
def target_wire(monkeypatch):
    original_client = httpx.AsyncClient
    captured = []
    expected = [("from", "2026-09-20"), ("to", "2026-11-24")]

    def install(payload, status=200):
        def respond(request):
            captured.append(request)
            assert request.method == "GET"
            assert request.url.scheme == "https"
            assert request.url.host == "www.polaraccesslink.com"
            assert request.url.path == "/v4/data/training-target/calendar-targets"
            assert request.headers["Authorization"] == "Bearer synthetic-wire-token"
            if "from" not in request.url.params:
                return httpx.Response(400, json={"errorMessage": (
                    "Call to path training-target/calendar-targets with method GET failed "
                    "due to an invalid request: Query parameter 'from' is required"
                )})
            assert list(request.url.params.multi_items()) == expected
            return httpx.Response(status, json=payload)

        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(respond), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", client)

    def fetch(raw=False):
        # Target requests do not use settings; keep .env loading out of the test.
        client = PolarClient.__new__(PolarClient)
        return asyncio.run(client.list_training_targets(
            "synthetic-wire-token", date(2026, 9, 20), date(2026, 11, 24),
            raw_response=raw,
        ))

    return install, fetch, captured


@pytest.mark.parametrize("raw", [False, True])
def test_observed_missing_from_error_is_prevented_without_losing_source_fields(target_wire, raw):
    install, fetch, captured = target_wire
    targets = [{"session": {"id": "synthetic-target", "done": False},
                "exercise": [{"duration": 0}], "unknownNested": {"retained": True}}]
    payload = {"trainingTarget": targets, "unknownEnvelope": {"retained": True}}
    install(payload)
    assert fetch(raw) == (payload if raw else targets)
    assert len(captured) == 1


@pytest.mark.parametrize("payload", [[], {"trainingTarget": []}])
def test_empty_targets_remain_a_valid_empty_response(target_wire, payload):
    install, fetch, captured = target_wire
    install(payload)
    assert fetch() == []
    assert len(captured) == 1


@pytest.mark.parametrize("payload", [{}, {"trainingTarget": None}, {"trainingTarget": {}}])
def test_malformed_response_is_not_silently_reported_as_no_targets(target_wire, payload):
    install, fetch, captured = target_wire
    install(payload)
    with pytest.raises(PolarAPIError, match="POLAR_TARGETS_PAYLOAD_INVALID"):
        fetch()
    assert len(captured) == 1


@pytest.mark.parametrize("status", [400, 403, 429, 500])
def test_provider_rejection_retains_the_status_and_does_not_retry_with_other_dates(target_wire, status):
    install, fetch, captured = target_wire
    install({"errorMessage": "synthetic provider rejection"}, status)
    with pytest.raises(PolarAPIError, match="synthetic provider rejection") as failure:
        fetch()
    assert failure.value.status_code == status
    assert len(captured) == 1
