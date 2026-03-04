import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import String, Text, DateTime, select, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

def utcnow():
    return datetime.now(timezone.utc)

SQLITE_PATH = os.environ.get("SQLITE_PATH", "./qbo_mcp.sqlite3")
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_PATH}"

# Prefer DATABASE_URL for Postgres (or any SQLAlchemy URL); fall back to SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

class Base(DeclarativeBase):
    pass

class QBOCompanyConnection(Base):
    """One QBO OAuth connection per company (realm_id).

    This enables multiple admins/users in *your* app (Auth0 identities) to use
    the same connected QBO company without re-running Intuit OAuth per user.
    """

    __tablename__ = "qbo_company_connections"

    realm_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class QBOCompanyAccess(Base):
    """Which Auth0 users can use which QBO companies."""

    __tablename__ = "qbo_company_access"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    realm_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("qbo_company_connections.realm_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def delete_connection(user_id: str, realm_id: str) -> bool:
    """Remove a user's access to a company.

    If no users remain with access to that realm_id, the company connection row
    is also removed.
    """
    async with AsyncSessionLocal() as session:
        obj = await session.get(QBOCompanyAccess, {"user_id": user_id, "realm_id": realm_id})
        if not obj:
            return False
        await session.delete(obj)
        await session.commit()

        # If no one else has access, delete the company connection.
        remaining = await session.execute(
            select(func.count()).select_from(QBOCompanyAccess).where(QBOCompanyAccess.realm_id == realm_id)
        )
        if (remaining.scalar_one() or 0) == 0:
            conn = await session.get(QBOCompanyConnection, realm_id)
            if conn:
                await session.delete(conn)
                await session.commit()
        return True

async def upsert_company_connection(
    realm_id: str,
    company_name: Optional[str],
    access_token_enc: Optional[str],
    refresh_token_enc: str,
    access_token_expires_at: Optional[datetime],
) -> None:
    async with AsyncSessionLocal() as session:
        obj = await session.get(QBOCompanyConnection, realm_id)
        if obj is None:
            obj = QBOCompanyConnection(
                realm_id=realm_id,
                company_name=company_name,
                access_token_enc=access_token_enc,
                refresh_token_enc=refresh_token_enc,
                access_token_expires_at=access_token_expires_at,
                updated_at=utcnow(),
            )
            session.add(obj)
        else:
            if company_name:
                obj.company_name = company_name
            obj.access_token_enc = access_token_enc
            obj.refresh_token_enc = refresh_token_enc
            obj.access_token_expires_at = access_token_expires_at
            obj.updated_at = utcnow()
        await session.commit()


async def grant_access(user_id: str, realm_id: str, role: str = "admin") -> None:
    async with AsyncSessionLocal() as session:
        obj = await session.get(QBOCompanyAccess, {"user_id": user_id, "realm_id": realm_id})
        if obj is None:
            obj = QBOCompanyAccess(user_id=user_id, realm_id=realm_id, role=role, created_at=utcnow())
            session.add(obj)
        else:
            obj.role = role or obj.role
        await session.commit()


async def upsert_connection(
    user_id: str,
    realm_id: str,
    company_name: Optional[str],
    access_token_enc: Optional[str],
    refresh_token_enc: str,
    access_token_expires_at: Optional[datetime],
) -> None:
    """Back-compat shim: update company connection + ensure the user has access."""
    await upsert_company_connection(
        realm_id=realm_id,
        company_name=company_name,
        access_token_enc=access_token_enc,
        refresh_token_enc=refresh_token_enc,
        access_token_expires_at=access_token_expires_at,
    )
    await grant_access(user_id=user_id, realm_id=realm_id, role="admin")

async def list_connections(user_id: str) -> List[Dict[str, Any]]:
    """List companies a user has access to (kept for backward compatibility)."""
    return await list_user_companies(user_id)


async def list_user_companies(user_id: str) -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(QBOCompanyConnection, QBOCompanyAccess)
            .join(QBOCompanyAccess, QBOCompanyAccess.realm_id == QBOCompanyConnection.realm_id)
            .where(QBOCompanyAccess.user_id == user_id)
            .order_by(QBOCompanyConnection.updated_at.desc())
        )
        res = await session.execute(stmt)
        rows = res.all()
        out: List[Dict[str, Any]] = []
        for conn, acc in rows:
            out.append(
                {
                    "realm_id": conn.realm_id,
                    "company_name": conn.company_name,
                    "updated_at": conn.updated_at.isoformat(),
                    "role": acc.role,
                }
            )
        return out

async def user_has_access(user_id: str, realm_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        obj = await session.get(QBOCompanyAccess, {"user_id": user_id, "realm_id": realm_id})
        return obj is not None


async def get_company_connection(realm_id: str) -> Dict[str, Any]:
    async with AsyncSessionLocal() as session:
        obj = await session.get(QBOCompanyConnection, realm_id)
        if not obj:
            raise ValueError("Company not connected")
        return {
            "realm_id": obj.realm_id,
            "company_name": obj.company_name,
            "access_token_enc": obj.access_token_enc,
            "refresh_token_enc": obj.refresh_token_enc,
            "access_token_expires_at": obj.access_token_expires_at,
            "updated_at": obj.updated_at,
        }


async def get_connection(user_id: str, realm_id: str) -> Dict[str, Any]:
    """Back-compat shim: validate access, then return the company connection."""
    if not await user_has_access(user_id, realm_id):
        raise ValueError("Not connected")
    return await get_company_connection(realm_id)
