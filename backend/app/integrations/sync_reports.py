import argparse
import json
from dataclasses import asdict

from app.db.session import SessionLocal
from app.integrations.microsoft_graph import MicrosoftGraphClient
from app.services.microsoft_graph_sync import sync_microsoft_graph


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Microsoft Graph usage and license reports."
    )
    parser.add_argument(
        "--period",
        choices=("D7", "D90", "D180"),
        default="D90",
        help="Rolling report period to download (default: D90).",
    )
    args = parser.parse_args()

    client = MicrosoftGraphClient()
    with SessionLocal() as db:
        result = sync_microsoft_graph(db, client, args.period)
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
