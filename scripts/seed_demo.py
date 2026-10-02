# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""Give a demo account follows so its feed is ranked and its alert path runs for real.

Everything goes through the public gateway API, exactly as the web app would: sign in,
read the feed, follow the headliners of the soonest shows that have genre data. Each follow
publishes users.taste_updated, so the matcher queues alerts and the live feed pushes them.
Safe to re-run (follows are idempotent).

    uv run scripts/seed_demo.py --gateway https://api.<host>.sslip.io
    uv run scripts/seed_demo.py                      # local gateway on :8000
"""

import argparse
import sys

import httpx


def main() -> int:
    """Parse arguments, seed the demo account, and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gateway", default="http://localhost:8000", help="gateway base URL")
    parser.add_argument("--email", default="demo@concertradar.dev", help="demo account email")
    parser.add_argument("--follows", type=int, default=5, help="headliners to follow")
    args = parser.parse_args()

    with httpx.Client(base_url=args.gateway, timeout=30.0) as client:
        login = client.post("/auth/dev", json={"email": args.email})
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['token']}"

        feed = client.get("/feed", params={"limit": 100})
        feed.raise_for_status()
        items = feed.json()["items"]
        if not items:
            print("The feed is empty: run a scrape first so there are shows to follow.")
            return 1

        followed = pick_headliners(items, args.follows)
        for artist_id, name in followed:
            client.post("/follows", json={"artist_id": artist_id}).raise_for_status()
            print(f"followed {name}")

        ranked = client.get("/feed", params={"limit": 5})
        ranked.raise_for_status()
        print(f"\n{args.email} now follows {len(followed)} artists. Top of the feed:")
        for item in ranked.json()["items"]:
            print(f"  {item['score']:.2f}  {item['artist_name']} @ {item['venue_name']}")
    return 0


def pick_headliners(items: list[dict[str, object]], count: int) -> list[tuple[str, str]]:
    """Return up to `count` distinct (artist id, name) headliners with genres, soonest first."""
    # Score order changes as soon as the account follows someone, so pick by date to make
    # re-runs choose the same artists.
    by_date = sorted(items, key=lambda item: (str(item["starts_at"]), str(item["event_id"])))
    picked: dict[str, str] = {}
    for item in by_date:
        artist_id = str(item["artist_id"])
        if item["artist_genres"] and artist_id not in picked:
            picked[artist_id] = str(item["artist_name"])
        if len(picked) == count:
            break
    return list(picked.items())


if __name__ == "__main__":
    sys.exit(main())
