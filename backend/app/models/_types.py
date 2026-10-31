"""Shared column helpers. Server-side defaults mirror the migrations; Python never invents ids/timestamps."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

UUID_PK_DEFAULT = text("gen_random_uuid()")
NOW = text("now()")


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=UUID_PK_DEFAULT)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=NOW)


def updated_at() -> Mapped[datetime]:
    """Stamped by trg_<table>_updated_at on UPDATE; never set in code."""
    return mapped_column(DateTime(timezone=True), server_default=NOW)
