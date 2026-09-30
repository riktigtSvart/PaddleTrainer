from datetime import date
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

AUTH_BASE = "https://auth.polar.com"
DATA_BASE = "https://www.polaraccesslink.com/v4/data"


class PolarAPIError(RuntimeError):
    pass


class PolarClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.polar_client_id,
            "response_type": "code",
            "scope": " ".join(self.settings.polar_scope_list),
            "redirect_uri": self.settings.polar_redirect_uri,
            "state": state,
        }
        return f"{AUTH_BASE}/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_BASE}/oauth/token",
                auth=(self.settings.polar_client_id, self.settings.polar_client_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.polar_redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        return self._json_or_raise(response)

    async def refresh_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_BASE}/oauth/token",
                auth=(self.settings.polar_client_id, self.settings.polar_client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json"},
            )
        return self._json_or_raise(response)


    async def list_training_sessions(
            self,
            access_token: str,
            from_date: date,
            to_date: date,
            features: list[str] | None = None,
    ) -> dict:
        from_value = f"{from_date.isoformat()}T00:00:00"
        to_value = f"{to_date.isoformat()}T00:00:00"

        params: list[tuple[str, str]] = [
            ("from", from_value),
            ("to", to_value),
        ]

        for feature in features or []:
            params.append(("features", feature))

        return await self._get(
            access_token,
            "/training-sessions/list",
            params=params,
        )

    async def list_training_targets(
        self,
        access_token: str,
        from_date: date,
        to_date: date,
    ) -> dict:
        params = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        }
        return await self._get(
            access_token,
            "/training-target/calendar-targets",
            params=params,
        )

    async def list_sport_profiles(self, access_token: str) -> dict:
        return await self._get(access_token, "/sports/profiles")

    async def list_nightly_recharge_results(
        self,
        access_token: str,
        from_date: date,
        to_date: date,
        features: list[str] | None = None,
    ) -> dict:
        params: list[tuple[str, str]] = [
            ("from", from_date.isoformat()),
            ("to", to_date.isoformat()),
        ]

        for feature in features or []:
            params.append(
                ("features", feature)
            )

        return await self._get(
            access_token,
            "/nightly-recharge-results",
            params=params,
        )


    async def list_sleeps(
        self,
        access_token: str,
        from_date: date,
        to_date: date,
        features: list[str] | None = None,
    ) -> dict:
        params: list[tuple[str, str]] = [
            ("from", from_date.isoformat()),
            ("to", to_date.isoformat()),
        ]

        for feature in features or []:
            params.append(
                ("features", feature)
            )

        return await self._get(
            access_token,
            "/sleeps",
            params=params,
        )

    async def list_continuous_samples(
        self,
        access_token: str,
        from_date: date,
        to_date: date,
        features: list[str] | None = None,
    ) -> dict:
        params: list[tuple[str, str]] = [
            ("from", from_date.isoformat()),
            ("to", to_date.isoformat()),
        ]

        for feature in features or []:
            params.append(
                ("features", feature)
            )

        return await self._get(
            access_token,
            "/continuous-samples",
            params=params,
        )

    async def _get(self, access_token: str, path: str, params=None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{DATA_BASE}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            print("POLAR REQUEST:", response.request.url)
            print("POLAR STATUS:", response.status_code)

        return self._json_or_raise(response)

    async def list_sports(self, access_token: str) -> dict:
        return await self._get(
            access_token,
            "/sports/list",
        )

    @staticmethod
    def _json_or_raise(response: httpx.Response) -> dict:
        if response.is_success:
            return response.json() if response.content else {}

        try:
            detail = response.json()
        except ValueError:
            detail = response.text

        raise PolarAPIError(
            f"Polar API {response.status_code}: {detail}"
        )
