"""Migrate module scripts into script_configs rows for all clients."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from db import postgres as pg_db
from script_module_export import export_module

load_dotenv(_ROOT / ".env")


@dataclass
class MigrationResult:
    client_id: str
    route: str
    script_id: str
    action: str
    script_config_id: str | None
    detail: str = ""


async def _discover_targets(pool) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT DISTINCT client_id, route, script_id
        FROM bot_configs
        WHERE active = TRUE
        ORDER BY client_id, route, script_id
        """
    )
    return [dict(r) for r in rows]


async def _get_existing_script_config(pool, client_id: UUID, script_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT * FROM script_configs
        WHERE client_id = $1 AND script_id = $2
        """,
        client_id,
        script_id,
    )
    return pg_db.record_to_dict(row)


async def _link_bot_configs(
    pool, *, client_id: UUID, route: str, script_id: str, script_config_id: UUID
) -> int:
    result = await pool.execute(
        """
        UPDATE bot_configs
        SET script_config_id = $4
        WHERE client_id = $1
          AND route = $2
          AND script_id = $3
          AND active = TRUE
        """,
        client_id,
        route,
        script_id,
        script_config_id,
    )
    return int(result.split()[-1])


async def migrate_script_configs(
    pool,
    *,
    dry_run: bool = False,
    force_update: bool = False,
    verify_only: bool = False,
) -> tuple[list[MigrationResult], list[str]]:
    targets = await _discover_targets(pool)
    results: list[MigrationResult] = []
    errors: list[str] = []

    for row in targets:
        client_id = UUID(str(row["client_id"]))
        route = str(row["route"])
        script_id = str(row["script_id"])
        label = f"client={client_id} route={route} script_id={script_id}"
        try:
            payload = export_module(route, script_id)
        except Exception as exc:
            errors.append(f"{label}: export failed: {exc}")
            results.append(
                MigrationResult(
                    str(client_id), route, script_id, "error", None, f"export failed: {exc}"
                )
            )
            continue

        if verify_only:
            results.append(
                MigrationResult(
                    str(client_id), route, script_id, "validated", None, "verify-only"
                )
            )
            continue
        if dry_run:
            results.append(
                MigrationResult(
                    str(client_id), route, script_id, "dry-run", None, "export validated"
                )
            )
            continue

        existing = await _get_existing_script_config(pool, client_id, script_id)
        if existing is None:
            try:
                created = await pg_db.create_script_config(pool, client_id, payload)
            except Exception as exc:
                errors.append(f"{label}: create failed: {exc}")
                results.append(
                    MigrationResult(
                        str(client_id), route, script_id, "error", None, f"create failed: {exc}"
                    )
                )
                continue
            sc_id = UUID(str(created["id"]))
            linked = await _link_bot_configs(
                pool,
                client_id=client_id,
                route=route,
                script_id=script_id,
                script_config_id=sc_id,
            )
            results.append(
                MigrationResult(
                    str(client_id),
                    route,
                    script_id,
                    "created",
                    str(sc_id),
                    f"linked_bot_configs={linked}",
                )
            )
            continue

        sc_id = UUID(str(existing["id"]))
        if force_update:
            try:
                await pg_db.update_script_config(pool, sc_id, client_id, payload)
                action = "updated"
            except Exception as exc:
                errors.append(f"{label}: update failed: {exc}")
                results.append(
                    MigrationResult(
                        str(client_id), route, script_id, "error", str(sc_id), f"update failed: {exc}"
                    )
                )
                continue
        else:
            action = "skipped"

        linked = await _link_bot_configs(
            pool,
            client_id=client_id,
            route=route,
            script_id=script_id,
            script_config_id=sc_id,
        )
        results.append(
            MigrationResult(
                str(client_id),
                route,
                script_id,
                action,
                str(sc_id),
                f"linked_bot_configs={linked}",
            )
        )

    return results, errors


def _print_results(results: list[MigrationResult], errors: list[str]) -> None:
    print("\nMigration summary:")
    for r in results:
        print(
            f"- {r.client_id} | {r.route:8} | {r.script_id:24} | {r.action:9} | "
            f"{r.script_config_id or '-'} | {r.detail}"
        )
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"- {err}")


async def _run(args: argparse.Namespace) -> int:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if not dsn:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 2

    pool = await pg_db.create_db_pool(dsn)
    try:
        results, errors = await migrate_script_configs(
            pool,
            dry_run=args.dry_run,
            force_update=args.force_update,
            verify_only=args.verify_only,
        )
    finally:
        await pg_db.close_pool()

    _print_results(results, errors)
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate module-based bot scripts into script_configs DB rows."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Export + validate only; no DB writes.",
    )
    p.add_argument(
        "--force-update",
        action="store_true",
        help="Update existing script_configs with exported payloads.",
    )
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate all discovered module exports only.",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
