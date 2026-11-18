from app.core.config import settings
from app.db.session import SessionLocal
from app.services.demo_data import seed_demo_data


def main() -> None:
    if settings.ENVIRONMENT.casefold() in {"prod", "production"}:
        raise RuntimeError(
            "Demo data cannot be seeded in a production environment."
        )

    with SessionLocal.begin() as db:
        seeded_user_count = seed_demo_data(db)

    if seeded_user_count:
        print(
            f"Seeded {seeded_user_count} fictional demo users and related "
            "dashboard records."
        )
    else:
        print("Demo data already exists; no changes were made.")


if __name__ == "__main__":
    main()
