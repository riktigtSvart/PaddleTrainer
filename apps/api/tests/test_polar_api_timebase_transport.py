"""Execute the actual transport functions with isolated database/provider doubles.

These tests also run without the full API runtime. HTTP-level tests live in
test_polar_api_timebase_api.py and use FastAPI's real TestClient.
"""

import ast
import asyncio
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from app.services.api_hr_timebase_audit import build_api_hr_timebase_audit


class GatewayError(RuntimeError):
    pass


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class Selection:
    def where(self, *args):
        return self


def transport():
    path = Path(__file__).resolve().parents[1] / "app/api/routes/polar_tcx.py"
    definitions = {"_fetch_sample_session", "inspect_training_session_api_timebase"}
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.AsyncFunctionDef) and n.name in definitions]
    for node in nodes:
        node.decorator_list = []
        node.returns = None
        for arg in node.args.args + node.args.kwonlyargs:
            arg.annotation = None
    provider = AsyncMock(return_value={"trainingSessions": []})
    user = AsyncMock(return_value=SimpleNamespace(id="synthetic-owner"))
    token = AsyncMock(return_value="synthetic-private-token")
    namespace = {"date": date, "timedelta": timedelta, "HTTPException": HttpError,
                 "PolarAPIError": GatewayError, "build_api_hr_timebase_audit": build_api_hr_timebase_audit,
                 "ExternalConnection": SimpleNamespace(user_id=None, provider=None),
                 "select": lambda model: Selection(), "get_or_create_demo_user": user,
                 "get_valid_access_token": token, "PolarClient": lambda: SimpleNamespace(list_training_sessions=provider)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), namespace)
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(scopes=["training_sessions:read"])))
    return SimpleNamespace(namespace=namespace, provider=provider, user=user, token=token, db=db)


class TransportTests(unittest.TestCase):
    def test_new_endpoint_requests_all_three_features_once_and_no_raw_by_default(self):
        t = transport()
        value = asyncio.run(t.namespace["inspect_training_session_api_timebase"]("synthetic-session", date(2026, 7, 3), t.db))
        t.provider.assert_awaited_once_with("synthetic-private-token", date(2026, 7, 3), date(2026, 7, 4), features=["samples", "routes", "pause-times"])
        self.assertIsNone(value["raw_session"])
        self.assertEqual(value["audit"]["status"], "WITHHELD")
        self.assertEqual(value["science_storage_writes"], 0)

    def test_existing_tcx_helper_default_is_still_samples_only(self):
        t = transport()
        asyncio.run(t.namespace["_fetch_sample_session"](t.db, "synthetic-session", date(2026, 7, 3)))
        self.assertEqual(t.provider.await_args.kwargs, {"features": ["samples"]})

    def test_id_selection_ignores_other_sessions_and_rejects_duplicates(self):
        t = transport()
        expected = {"identifier": {"id": "target"}, "exercises": []}
        t.provider.return_value = {"trainingSessions": [{"identifier": {"id": "other"}}, expected]}
        value = asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date(2026, 7, 3)))
        self.assertEqual(value[1:], (expected, 1))
        t.provider.return_value = {"trainingSessions": [expected, expected]}
        value = asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date(2026, 7, 3)))
        self.assertEqual(value[1:], (None, 2))

    def test_scope_and_connection_fail_before_token_or_provider(self):
        for connection, status in [(None, 404), (SimpleNamespace(scopes=[]), 403)]:
            t = transport()
            t.db.scalar.return_value = connection
            with self.assertRaises(HttpError) as captured:
                asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date(2026, 7, 3)))
            self.assertEqual(captured.exception.status_code, status)
            t.token.assert_not_awaited()
            t.provider.assert_not_awaited()

    def test_invalid_provider_shape_is_controlled(self):
        t = transport()
        t.provider.return_value = {"trainingSessions": {}}
        with self.assertRaises(HttpError) as captured:
            asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date(2026, 7, 3)))
        self.assertEqual(captured.exception.status_code, 502)

    def test_upstream_private_error_is_not_returned(self):
        t = transport()
        t.provider.side_effect = GatewayError("private details")
        with self.assertRaises(HttpError) as captured:
            asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date(2026, 7, 3)))
        self.assertEqual(captured.exception.status_code, 502)
        self.assertNotIn("private", captured.exception.detail)

    def test_terminal_date_is_rejected_before_owner_lookup(self):
        t = transport()
        with self.assertRaises(HttpError) as captured:
            asyncio.run(t.namespace["_fetch_sample_session"](t.db, "target", date.max))
        self.assertEqual(captured.exception.status_code, 422)
        t.user.assert_not_awaited()
        t.provider.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
