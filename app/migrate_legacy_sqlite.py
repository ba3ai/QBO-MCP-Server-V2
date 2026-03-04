"""One-time migration: legacy per-user connections -> per-company connection + access mapping.

Run with the same SQLITE_PATH / DATABASE_URL env vars as your app.

- Reads from legacy table: qbo_connections(user_id, realm_id, ...)
- Writes into:
  - qbo_company_connections(realm_id, ...)
  - qbo_company_access(user_id, realm_id, role)

Safe to re-run (idempotent-ish): it upserts rows.
"""

import asyncio

from sqlalchemy import text

from app.db import AsyncSessionLocal, init_db, upsert_company_connection, grant_access


async def main():
    await init_db()

    async with AsyncSessionLocal() as session:
        # Check legacy table exists
        try:
            await session.execute(text("SELECT 1 FROM qbo_connections LIMIT 1"))
        except Exception:
            print("No legacy table qbo_connections found. Nothing to migrate.")
            return

        rows = (await session.execute(text(
            "SELECT user_id, realm_id, company_name, access_token_enc, refresh_token_enc, access_token_expires_at, updated_at "
            "FROM qbo_connections"
        ))).mappings().all()

    if not rows:
        print("Legacy table is empty. Nothing to migrate.")
        return

    migrated = 0
    for r in rows:
        await upsert_company_connection(
            realm_id=r["realm_id"],
            company_name=r.get("company_name"),
            access_token_enc=r.get("access_token_enc"),
            refresh_token_enc=r["refresh_token_enc"],
            access_token_expires_at=r.get("access_token_expires_at"),
        )
        await grant_access(user_id=r["user_id"], realm_id=r["realm_id"], role="admin")
        migrated += 1

    print(f"✅ Migrated {migrated} legacy rows into per-company + access tables.")


if __name__ == "__main__":
    asyncio.run(main())
