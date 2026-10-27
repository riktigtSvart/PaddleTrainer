"""Repair an empty Polar plan block list from its exact stored, diagnostic-pinned source."""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from uuid import uuid4


async def run(arguments, expected):
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models.entities import User
    from app.services.polar_plan_projection_repair import ProjectionRepairError, repair
    try:
        async with SessionLocal() as db:
            try:
                user = (await db.execute(select(User.id).where(User.email == get_settings().demo_user_email))).scalar_one_or_none()
                if user is None: raise ProjectionRepairError("PROJECTION_OWNER_NOT_FOUND")
                owner = str(user)
            finally:
                await db.rollback()
        async with SessionLocal() as db:
            return await repair(db, owner=owner, expected=expected, apply=arguments.apply)
    finally:
        await engine.dispose()


def main():
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--plan-id")
    parser.add_argument("--output-dir", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not args.output_dir.is_dir(): parser.error("--output-dir must be an existing directory.")
    if not args.report.is_file() or args.report.stat().st_size > 2 * 1024 * 1024:
        parser.error("Select the original diagnostic JSON, no larger than 2 MiB.")
    if not (repo / "apps/api/app/services/polar_plan_projection_repair.py").is_file():
        parser.error("Apply P2.4C9R7 to the selected project first.")
    sys.path.insert(0, str(repo / "apps/api"))
    from app.services.polar_plan_projection_repair import ProjectionRepairError, expected_source
    try:
        original = json.loads(args.report.read_text(encoding="utf-8-sig"))
        expected = expected_source(original, args.plan_id)
        result = asyncio.run(run(args, expected))
    except ProjectionRepairError as exc:
        print("STOP:", str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print("STOP: projection repair failed (" + type(exc).__name__ + "). Inspect the database by rerunning --check before retrying.", file=sys.stderr)
        return 1
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = args.output_dir / f"PaddleTrainer_plan_blocks_{result['state']}_{stamp}_{uuid4().hex[:8]}.json"
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as output: output.write(encoded)
    except OSError:
        print("RESULT FILE COULD NOT BE SAVED. Database outcome: " + result["state"], file=sys.stderr)
        print(encoded)
        return 1
    print("CREATED:", destination)
    print("STATE:", result["state"], "BLOCKS:", result["existing_block_count"], "->", result["proposed_block_count"])
    if result["blocked_reason"]: print("BLOCKED:", result["blocked_reason"])
    print("No provider request, native-source edit, measurement edit or Git operation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
