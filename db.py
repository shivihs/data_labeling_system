import os
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

REVIEWERS_TABLE = "ysc_human_reviewers"
CHOICES = ("BOTH", "GPT", "GEMINI", "OWN")


def _client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SECRET_KEY in .env")
    return create_client(url, key)


def labels_table(test_mode: bool) -> str:
    return "ysc_human_labels_test" if test_mode else "ysc_human_labels"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_random_unrated(role: str, test_mode: bool) -> dict | None:
    sb = _client()
    table = labels_table(test_mode)
    choice_col = f"{role}_choice"

    res = (
        sb.table(table)
        .select("id", count="exact")
        .is_(choice_col, "null")
        .limit(1)
        .execute()
    )
    total = res.count or 0
    if total == 0:
        return None

    offset = random.randint(0, total - 1)
    res = (
        sb.table(table)
        .select("id, text, gpt_cat, gpt_just, gemini_cat, gemini_just")
        .is_(choice_col, "null")
        .range(offset, offset)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def save_choice(
    role: str,
    record_id: int,
    choice: str,
    cat: str | None,
    just: str | None,
    test_mode: bool,
) -> None:
    if choice not in CHOICES:
        raise ValueError(f"Invalid choice: {choice}")
    sb = _client()
    table = labels_table(test_mode)
    payload = {
        f"{role}_choice": choice,
        f"{role}_cat": cat if choice == "OWN" else None,
        f"{role}_just": just if choice == "OWN" else None,
        f"{role}_at": _now(),
    }
    sb.table(table).update(payload).eq("id", record_id).execute()


def get_max_id(test_mode: bool) -> int:
    sb = _client()
    table = labels_table(test_mode)
    res = sb.table(table).select("id").order("id", desc=True).limit(1).execute()
    rows = res.data or []
    return rows[0]["id"] if rows else 0


def get_stats(role: str, test_mode: bool) -> dict[str, int]:
    sb = _client()
    table = labels_table(test_mode)
    choice_col = f"{role}_choice"

    def _count(filter_fn) -> int:
        q = sb.table(table).select("id", count="exact")
        q = filter_fn(q)
        return q.limit(1).execute().count or 0

    total = _count(lambda q: q.not_.is_(choice_col, "null"))
    both = _count(lambda q: q.eq(choice_col, "BOTH"))
    gpt = _count(lambda q: q.eq(choice_col, "GPT"))
    gemini = _count(lambda q: q.eq(choice_col, "GEMINI"))
    own = _count(lambda q: q.eq(choice_col, "OWN"))
    return {
        "total": total,
        "both": both,
        "gpt": gpt,
        "gemini": gemini,
        "own": own,
    }
