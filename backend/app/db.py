import re
from urllib.parse import unquote

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base for models mapped to the EXISTING tables. Never call Base.metadata.create_all()."""


# scheme://credentials@rest. Greedy on purpose: credentials end at the LAST '@', so a password that
# contains a raw '@' (a common copy-paste from the Supabase dashboard) still parses correctly.
_URL_RE = re.compile(r"^(?P<scheme>[A-Za-z0-9+]+)://(?P<creds>.+)@(?P<rest>[^@]+)$")


def build_url(raw: str) -> URL:
    """Turn the DATABASE_URL from .env into a SQLAlchemy URL using the psycopg 3 driver.

    Accepts plain postgresql:// as Supabase shows it. Percent-encoded passwords are decoded;
    raw ones are used as is.
    """
    raw = raw.strip()
    # Tolerate a doubled scheme such as "postgresql+psycopg://postgresql://user:pw@host/db" (pasting a
    # Supabase string after a driver prefix); the inner URL is the real one.
    raw = re.sub(r"^[A-Za-z0-9+]+://(?=[A-Za-z0-9+]+://)", "", raw)
    m = _URL_RE.match(raw)
    if m is None:
        parsed = make_url(raw)
    else:
        user, _, password = m["creds"].partition(":")
        if re.search(r"%[0-9A-Fa-f]{2}", password):
            password = unquote(password)
        parsed = make_url(f"{m['scheme']}://{m['rest']}").set(username=unquote(user), password=password or None)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed


engine = create_engine(
    build_url(get_settings().database_url),
    pool_pre_ping=True,
    # Supabase's transaction pooler (pgbouncer) cannot keep server-side prepared statements.
    connect_args={"prepare_threshold": None},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
