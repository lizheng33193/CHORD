"""Initialize auth database schema and seed data."""

from __future__ import annotations

from app.auth.database import AuthSessionLocal, create_auth_schema
from app.auth.seed import seed_auth_data


def main() -> None:
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)
    print("Auth database initialized and seeded.")


if __name__ == "__main__":
    main()
