"""DEMO ONLY: adds 4 days of fake usage so the habit suggestion can be shown in a review.

Real habits need about 3 days of normal use to appear. Run this to demonstrate the
feature immediately, and tell the reviewers the data is seeded.

    python -m scripts.seed_demo_habits          (add demo data)
    python -m scripts.seed_demo_habits --clear  (remove it again)
"""
import sys
from contextlib import closing
from datetime import datetime, timedelta

from memory.database import get_connection

STEPS = ["app: vs code", "folder: notes", "search: youtube | lofi music"]
TAG_SECONDS = 7  # demo rows are stamped at hh:mm:07 so --clear removes only them


def main():
    with closing(get_connection()) as connection:
        if "--clear" in sys.argv:
            connection.execute("DELETE FROM usage_log WHERE strftime('%S', created_at) = '07'")
            connection.execute("DELETE FROM dismissed_suggestions")
            connection.commit()
            print("Demo habits removed.")
            return
        hour = datetime.now().hour
        for days_ago in range(1, 5):
            day = datetime.now() - timedelta(days=days_ago)
            for minute, step in enumerate(STEPS):
                stamp = day.replace(hour=hour, minute=minute * 3, second=TAG_SECONDS, microsecond=0)
                connection.execute(
                    "INSERT INTO usage_log (step, created_at) VALUES (?, ?)",
                    (step, stamp.strftime("%Y-%m-%d %H:%M:%S")),
                )
        connection.commit()
    print(f"Seeded 4 days of demo habits at {hour}:00. Restart JARVIS to see the suggestion.")


if __name__ == "__main__":
    main()
