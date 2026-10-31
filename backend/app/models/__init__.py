"""Import every model module so Base.metadata knows all tables and string relationships resolve."""
from app.models import billing, catalogue, discounts, identity, subscriptions  # noqa: F401
