"""Inspect one local day and optionally the matching Polar API day; never import."""
import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys
from uuid import uuid4


async def collect(arguments):
    from sqlalchemy import select, text
    from app.core.config import get_settings
    from app.core.security import decrypt_secret
    from app.db.session import SessionLocal, engine
    from app.integrations.polar.client import PolarClient
    from app.models.entities import ExternalConnection, User
    from app.services.polar_phase_diagnostic import findings, local_report, provider_report

    report = None
    access, scopes, usable = None, [], False
    try:
        async with SessionLocal() as db:
            try:
                if db.get_bind().dialect.name == "postgresql":
                    await db.execute(text("SET TRANSACTION READ ONLY"))
                user = (await db.execute(select(User).where(User.email == get_settings().demo_user_email))).scalar_one_or_none()
                if user is None:
                    raise ValueError("DIAGNOSTIC_OWNER_NOT_FOUND")
                report = await local_report(db, user, arguments.date)
                connection = (await db.execute(select(ExternalConnection).where(
                    ExternalConnection.user_id == user.id, ExternalConnection.provider == "POLAR"))).scalar_one_or_none()
                if connection:
                    expires = connection.expires_at
                    if expires is not None and expires.tzinfo is None:
                        expires = expires.replace(tzinfo=UTC)
                    usable = expires is not None and expires > datetime.now(UTC) + timedelta(minutes=2)
                    scopes = list(connection.scopes or [])
                    if arguments.fetch_provider and usable:
                        access = decrypt_secret(connection.access_token_encrypted)
            finally:
                await db.rollback()
        if arguments.fetch_provider:
            report["provider"] = (await provider_report(PolarClient(), access, scopes, arguments.date)) if access and usable else {
                "requested": False, "reason": "VALID_ACCESS_NOT_AVAILABLE",
                "next_step": "Run the ordinary app synchronization to renew access, then repeat this diagnostic. This tool never refreshes credentials."}
        report["created_at_utc"] = datetime.now(UTC).isoformat()
        report["findings"] = findings(report)
        return report
    finally:
        await engine.dispose()


def main():
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fetch-provider", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not (repo / "apps/api/app/services/polar_phase_diagnostic.py").is_file():
        parser.error("Apply P2.4C9R6 to the selected project before running this diagnostic.")
    if not args.output_dir.is_dir():
        parser.error("--output-dir must be an existing directory.")
    sys.path.insert(0, str(repo / "apps/api"))
    try:
        report = asyncio.run(collect(args))
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = args.output_dir / f"PaddleTrainer_polar_phases_{args.date.isoformat()}_{stamp}_{uuid4().hex[:8]}.json"
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with destination.open("x", encoding="utf-8", newline="\n") as output:
            output.write(encoded)
        print("CREATED:", destination)
        print("READ ONLY: no source changes, import, token refresh, DB writes or Git operations.")
        if args.fetch_provider and not report["provider"]["requested"]:
            print("Provider not queried: valid access unavailable. Run the ordinary app sync, then retry.")
        return 0
    except Exception as exc:
        # Do not print connection strings, token data, provider bodies or tracebacks.
        print("STOP: phase diagnostic failed (" + type(exc).__name__ + "). No report was completed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
