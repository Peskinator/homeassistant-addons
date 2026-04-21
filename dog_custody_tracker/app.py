from __future__ import annotations

import base64
import json
import mimetypes
import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_DATA_DIR = Path("/data") if BASE_DIR == Path("/app") else (BASE_DIR / "data")
DATA_DIR = Path(os.environ.get("DOG_WALK_DATA_DIR") or str(DEFAULT_DATA_DIR))
DB_PATH = DATA_DIR / "dog_walks.sqlite3"
ACTIVITY_LOG_PATH = DATA_DIR / "activity.jsonl"
WRITE_DEBUG_LOG_PATH = DATA_DIR / "write_debug.jsonl"
PUSH_DEBUG_LOG_PATH = DATA_DIR / "push_debug.jsonl"
VAPID_PRIVATE_KEY_PATH = DATA_DIR / "vapid_private_key.pem"
DEFAULT_PORT = 8420
VAPID_SUBJECT = "mailto:francois.pesqui@gmail.com"
DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%A, %B %d, %Y",
    "%B %d, %Y",
)

PARTICIPANTS = (
    {
        "id": "frank",
        "display_name": "Frank",
        "short_name": "F",
        "color": "#557fa7",
        "accent": "#a7bfd6",
        "photo": "/frank.jpg",
    },
    {
        "id": "kurt",
        "display_name": "Kurt",
        "short_name": "K",
        "color": "#74634d",
        "accent": "#c5b49b",
        "photo": "/kurt.jpg",
    },
)

def canonical_email(value: str | None) -> str:
    email = (value or "").strip().lower()
    if "@" not in email:
        return email
    local_part, domain = email.split("@", 1)
    if domain in {"gmail.com", "googlemail.com"}:
        local_part = local_part.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local_part}@{domain}"


ACTOR_EMAILS = {
    canonical_email("francois.pesqui@gmail.com"): {"id": "frank", "name": "Frank"},
    canonical_email("kurt.zuo@gmail.com"): {"id": "kurt", "name": "Kurt"},
}


def app_version() -> str:
    config_path = BASE_DIR / "config.yaml"
    if config_path.exists():
        match = re.search(r'^version:\s*"([^"]+)"', config_path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return match.group(1)
    return os.environ.get("DOG_WALK_APP_VERSION", "dev")


APP_VERSION = app_version()
APP_MODE = "PROD" if BASE_DIR == Path("/app") else "TEST"
STATS_RANGES = {
    "7": 7,
    "30": 30,
    "90": 90,
    "365": 365,
    "all": None,
}


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def format_short_date(value: str) -> str:
    return parse_date(value).strftime("%b %d").replace(" 0", " ")


def daterange_dates(start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError("End date must be on or after start date.")
    current = start
    items: list[str] = []
    while current <= end:
        items.append(current.isoformat())
        current += timedelta(days=1)
    return items


def summarize_dates(dates: list[str]) -> str:
    normalized = sorted({parse_date(item).isoformat() for item in dates})
    if not normalized:
        return "selected days"
    if len(normalized) == 1:
        return format_short_date(normalized[0])
    start = parse_date(normalized[0])
    end = parse_date(normalized[-1])
    if (end - start).days + 1 == len(normalized):
        if start.year == end.year and start.month == end.month:
            return f"{start.strftime('%b')} {start.day}\u2013{end.day}"
        if start.year == end.year:
            return f"{start.strftime('%b')} {start.day}\u2013{end.strftime('%b')} {end.day}"
        return f"{start.strftime('%b')} {start.day}, {start.year}\u2013{end.strftime('%b')} {end.day}, {end.year}"
    if len(normalized) == 2:
        return f"{format_short_date(normalized[0])} and {format_short_date(normalized[1])}"
    return f"{format_short_date(normalized[0])}, {format_short_date(normalized[1])}, +{len(normalized) - 2} more"


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def vapid_material() -> dict[str, str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not VAPID_PRIVATE_KEY_PATH.exists():
        private_key = ec.generate_private_key(ec.SECP256R1())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        VAPID_PRIVATE_KEY_PATH.write_bytes(pem)

    private_pem = VAPID_PRIVATE_KEY_PATH.read_bytes()
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    public_key = private_key.public_key().public_numbers()
    public_bytes = b"\x04" + public_key.x.to_bytes(32, "big") + public_key.y.to_bytes(32, "big")
    return {
        "public_key": b64url_encode(public_bytes),
        "private_key_path": str(VAPID_PRIVATE_KEY_PATH),
        "subject": VAPID_SUBJECT,
    }


def jwt_email(header_value: str | None) -> str | None:
    if not header_value:
        return None
    parts = header_value.split(".")
    if len(parts) < 2:
        return None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    email = payload.get("email")
    if isinstance(email, str) and email.strip():
        return canonical_email(email)
    return None


def cookie_value(cookie_header: str | None, name: str) -> str | None:
    if not cookie_header:
        return None
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key.strip() == name:
            return value.strip()
    return None


def parse_date(value: str) -> date:
    cleaned = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def month_bounds(month_key: str) -> tuple[date, date]:
    month_start = datetime.strptime(month_key, "%Y-%m").date().replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1, day=1)
    return month_start, next_month


def detect_delimiter(csv_text: str) -> str:
    header = csv_text.splitlines()[0] if csv_text.splitlines() else ""
    if header.count(";") > header.count(","):
        return ";"
    return ","


def is_marked(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"x", "1", "true", "yes", "y"}


def google_sheet_export_url(sheet_url: str, gid: str = "0") -> str:
    parsed = urlparse(sheet_url)
    if "docs.google.com" not in parsed.netloc:
        raise ValueError("This importer only supports Google Sheets URLs.")

    if parsed.path.endswith("/export"):
        return sheet_url

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", parsed.path)
    if not match:
        raise ValueError("Could not extract a Google Sheets document id from that URL.")

    query = parse_qs(parsed.query)
    export_gid = query.get("gid", [gid])[0]
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={export_gid}"


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length).decode("utf-8") if content_length else "{}"
    return json.loads(raw or "{}")


class DogWalkStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.activity_log_path = ACTIVITY_LOG_PATH
        self.write_debug_log_path = WRITE_DEBUG_LOG_PATH
        self.push_debug_log_path = PUSH_DEBUG_LOG_PATH
        self.activity_lock = threading.Lock()
        self.write_debug_lock = threading.Lock()
        self.push_debug_lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS participants (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    short_name TEXT NOT NULL,
                    color TEXT NOT NULL,
                    accent TEXT NOT NULL,
                    photo TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS walk_entries (
                    walk_date TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL REFERENCES participants(id),
                    source TEXT NOT NULL DEFAULT 'manual',
                    notes TEXT,
                    weather_summary TEXT,
                    temperature_c REAL,
                    pain_index REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS device_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id TEXT NOT NULL REFERENCES participants(id),
                    endpoint TEXT NOT NULL UNIQUE,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

            for participant in PARTICIPANTS:
                connection.execute(
                    """
                    INSERT INTO participants (id, display_name, short_name, color, accent, photo)
                    VALUES (:id, :display_name, :short_name, :color, :accent, :photo)
                    ON CONFLICT(id) DO UPDATE SET
                        display_name=excluded.display_name,
                        short_name=excluded.short_name,
                        color=excluded.color,
                        accent=excluded.accent,
                        photo=excluded.photo
                    """,
                    participant,
                )

            connection.commit()

    def replace_database_bytes(self, content: bytes) -> dict[str, Any]:
        if not content:
            raise ValueError("Uploaded database file is empty.")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="dog-walks-", suffix=".sqlite3", dir=str(self.db_path.parent))
        os.close(fd)
        temp_path = Path(temp_name)

        try:
            temp_path.write_bytes(content)
            with closing(sqlite3.connect(temp_path)) as connection:
                cursor = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'walk_entries'"
                )
                if cursor.fetchone() is None:
                    raise ValueError("Uploaded file is not a valid dog tracker database.")
                row_count = int(connection.execute("SELECT COUNT(*) FROM walk_entries").fetchone()[0])
            os.replace(temp_path, self.db_path)
            self._initialize()
            return {"ok": True, "rows": row_count}
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def participants(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT id, display_name, short_name, color, accent, photo FROM participants ORDER BY display_name"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_month_payload(
        self,
        month_key: str,
        range_start: str | None = None,
        range_end: str | None = None,
    ) -> dict[str, Any]:
        month_start, next_month = month_bounds(month_key)
        entry_start = parse_date(range_start).isoformat() if range_start else month_start.isoformat()
        entry_end = parse_date(range_end).isoformat() if range_end else next_month.isoformat()
        with closing(self.connect()) as connection:
            month_rows = connection.execute(
                """
                SELECT walk_date, participant_id, source, notes, weather_summary, temperature_c, pain_index
                FROM walk_entries
                WHERE walk_date >= ? AND walk_date < ?
                ORDER BY walk_date
                """,
                (entry_start, entry_end),
            ).fetchall()
            totals_rows = connection.execute(
                """
                SELECT participant_id, COUNT(*) AS total
                FROM walk_entries
                GROUP BY participant_id
                ORDER BY participant_id
                """
            ).fetchall()

        totals = {participant["id"]: 0 for participant in PARTICIPANTS}
        for row in totals_rows:
            totals[row["participant_id"]] = row["total"]

        leader_id = None
        lead_delta = 0
        if len(totals) >= 2:
            ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
            leader_id = ordered[0][0]
            lead_delta = ordered[0][1] - ordered[1][1]

        entries = []
        for row in month_rows:
            item = dict(row)
            item["is_future"] = row["walk_date"] > date.today().isoformat()
            entries.append(item)

        return {
            "month": month_key,
            "today": date.today().isoformat(),
            "participants": self.participants(),
            "entries": entries,
            "totals": totals,
            "leader_id": leader_id,
            "lead_delta": lead_delta,
        }

    def diagnostic_payload(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "db_size": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "base_dir": str(BASE_DIR),
            "data_dir": str(DATA_DIR),
            "cwd": os.getcwd(),
            "env_data_dir": os.environ.get("DOG_WALK_DATA_DIR"),
        }
        try:
            with closing(self.connect()) as connection:
                cursor = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'walk_entries'"
                )
                has_entries_table = cursor.fetchone() is not None
                info["has_walk_entries_table"] = has_entries_table
                info["row_count"] = int(connection.execute("SELECT COUNT(*) FROM walk_entries").fetchone()[0]) if has_entries_table else 0
        except sqlite3.DatabaseError as exc:
            info["database_error"] = str(exc)
        return info

    def get_entry(self, walk_date: str) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT walk_date, participant_id, source, notes, weather_summary, temperature_c, pain_index
                FROM walk_entries
                WHERE walk_date = ?
                """,
                (walk_date,),
            ).fetchone()
        return dict(row) if row else None

    def append_activity(
        self,
        *,
        actor: dict[str, Any],
        walk_date: str,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        payload = {
            "timestamp": utcnow_iso(),
            "actor_id": actor.get("id", "unknown"),
            "actor_name": actor.get("name", "Unknown"),
            "actor_email": actor.get("email"),
            "actor_source": actor.get("source", "unknown"),
            "walk_date": walk_date,
            "action": action,
            "before_participant_id": before.get("participant_id") if before else None,
            "before_source": before.get("source") if before else None,
            "after_participant_id": after.get("participant_id") if after else None,
            "after_source": after.get("source") if after else None,
        }
        self.activity_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.activity_lock:
            with self.activity_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def recent_activity(self, limit: int = 80) -> list[dict[str, Any]]:
        if not self.activity_log_path.exists():
            return []
        lines = self.activity_log_path.read_text(encoding="utf-8").splitlines()
        items: list[dict[str, Any]] = []
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                items.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue
            if len(items) >= limit:
                break
        return items

    def append_write_debug(self, payload: dict[str, Any]) -> None:
        self.write_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.write_debug_lock:
            with self.write_debug_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def recent_write_debug(self, limit: int = 80) -> list[dict[str, Any]]:
        if not self.write_debug_log_path.exists():
            return []
        lines = self.write_debug_log_path.read_text(encoding="utf-8").splitlines()
        items: list[dict[str, Any]] = []
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                items.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue
            if len(items) >= limit:
                break
        return items

    def append_push_debug(self, payload: dict[str, Any]) -> None:
        self.push_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.push_debug_lock:
            with self.push_debug_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def recent_push_debug(self, limit: int = 80) -> list[dict[str, Any]]:
        if not self.push_debug_log_path.exists():
            return []
        lines = self.push_debug_log_path.read_text(encoding="utf-8").splitlines()
        items: list[dict[str, Any]] = []
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                items.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue
            if len(items) >= limit:
                break
        return items

    def correct_activity_entries(self, corrections: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.activity_log_path.exists():
            raise ValueError("Activity log does not exist yet.")

        normalized_corrections = []
        for correction in corrections:
            timestamp = str(correction.get("timestamp") or "").strip()
            walk_date = str(correction.get("walk_date") or "").strip()
            actor_id = str(correction.get("actor_id") or "").strip().lower()
            actor = next((item for item in PARTICIPANTS if item["id"] == actor_id), None)
            if not timestamp or not walk_date or not actor:
                raise ValueError("Each correction needs timestamp, walk_date, and a valid actor_id.")
            normalized_corrections.append(
                {
                    "timestamp": timestamp,
                    "walk_date": walk_date,
                    "actor_id": actor["id"],
                    "actor_name": actor["display_name"],
                    "actor_email": correction.get("actor_email"),
                    "actor_source": correction.get("actor_source") or "manual_correction",
                }
            )

        rows = []
        updated = 0
        with self.activity_lock:
            for raw_line in self.activity_log_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    item = json.loads(raw_line)
                except json.JSONDecodeError:
                    rows.append(raw_line)
                    continue

                match = next(
                    (
                        correction
                        for correction in normalized_corrections
                        if item.get("timestamp") == correction["timestamp"]
                        and item.get("walk_date") == correction["walk_date"]
                    ),
                    None,
                )
                if match:
                    item["actor_id"] = match["actor_id"]
                    item["actor_name"] = match["actor_name"]
                    item["actor_email"] = match["actor_email"]
                    item["actor_source"] = match["actor_source"]
                    updated += 1
                rows.append(json.dumps(item, ensure_ascii=True))

            self.activity_log_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")

        return {"ok": True, "updated": updated}

    def stats_payload(self, range_key: str = "90") -> dict[str, Any]:
        if range_key not in STATS_RANGES:
            raise ValueError("Unsupported stats range.")

        today = date.today()
        day_count = STATS_RANGES[range_key]
        if day_count is None:
            with closing(self.connect()) as connection:
                first_row = connection.execute(
                    "SELECT MIN(walk_date) AS first_date FROM walk_entries WHERE walk_date <= ?",
                    (today.isoformat(),),
                ).fetchone()
            range_start = parse_date(first_row["first_date"]) if first_row and first_row["first_date"] else today
        else:
            range_start = today - timedelta(days=day_count - 1)

        range_start_iso = range_start.isoformat()
        today_iso = today.isoformat()

        with closing(self.connect()) as connection:
            before_rows = connection.execute(
                """
                SELECT participant_id, COUNT(*) AS total
                FROM walk_entries
                WHERE walk_date < ? AND walk_date <= ?
                GROUP BY participant_id
                """,
                (range_start_iso, today_iso),
            ).fetchall()
            daily_rows = connection.execute(
                """
                SELECT walk_date, participant_id, COUNT(*) AS total
                FROM walk_entries
                WHERE walk_date >= ? AND walk_date <= ?
                GROUP BY walk_date, participant_id
                ORDER BY walk_date, participant_id
                """,
                (range_start_iso, today_iso),
            ).fetchall()
            monthly_rows = connection.execute(
                """
                SELECT substr(walk_date, 1, 7) AS month_key, participant_id, COUNT(*) AS total
                FROM walk_entries
                WHERE walk_date >= ? AND walk_date <= ?
                GROUP BY month_key, participant_id
                ORDER BY month_key, participant_id
                """,
                (range_start_iso, today_iso),
            ).fetchall()

        participants = self.participants()
        participant_ids = [participant["id"] for participant in participants]
        totals_before = {participant_id: 0 for participant_id in participant_ids}
        for row in before_rows:
            totals_before[row["participant_id"]] = int(row["total"])

        totals_in_range = {participant_id: 0 for participant_id in participant_ids}
        daily_lookup: dict[str, dict[str, int]] = {}
        for row in daily_rows:
            walk_date = row["walk_date"]
            participant_id = row["participant_id"]
            count = int(row["total"])
            daily_lookup.setdefault(walk_date, {})[participant_id] = count
            totals_in_range[participant_id] += count

        labels: list[str] = []
        balance_series: list[int] = []
        cumulative_series = {participant_id: [] for participant_id in participant_ids}
        running_totals = totals_before.copy()

        cursor = range_start
        while cursor <= today:
            walk_date = cursor.isoformat()
            labels.append(walk_date)
            day_counts = daily_lookup.get(walk_date, {})
            for participant_id in participant_ids:
                running_totals[participant_id] += day_counts.get(participant_id, 0)
                cumulative_series[participant_id].append(running_totals[participant_id])
            frank_total = running_totals.get("frank", 0)
            kurt_total = running_totals.get("kurt", 0)
            balance_series.append(frank_total - kurt_total)
            cursor += timedelta(days=1)

        monthly_labels = sorted({row["month_key"] for row in monthly_rows})
        monthly_totals = {
            participant_id: {month_key: 0 for month_key in monthly_labels}
            for participant_id in participant_ids
        }
        for row in monthly_rows:
            monthly_totals[row["participant_id"]][row["month_key"]] = int(row["total"])

        biggest_frank_lead = max(balance_series) if balance_series else 0
        biggest_kurt_lead = min(balance_series) if balance_series else 0

        return {
            "ok": True,
            "range_key": range_key,
            "range_start": range_start_iso,
            "range_end": today_iso,
            "participants": participants,
            "labels": labels,
            "balance_series": balance_series,
            "cumulative_series": cumulative_series,
            "monthly_labels": monthly_labels,
            "monthly_totals": monthly_totals,
            "totals_in_range": totals_in_range,
            "summary": {
                "current_balance": balance_series[-1] if balance_series else 0,
                "frank_total": totals_in_range.get("frank", 0),
                "kurt_total": totals_in_range.get("kurt", 0),
                "biggest_frank_lead": biggest_frank_lead,
                "biggest_kurt_lead": abs(biggest_kurt_lead),
            },
        }

    def upsert_subscription(
        self,
        *,
        participant_id: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO device_subscriptions (participant_id, endpoint, p256dh, auth, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    participant_id=excluded.participant_id,
                    p256dh=excluded.p256dh,
                    auth=excluded.auth
                """,
                (participant_id, endpoint, p256dh, auth, now),
            )
            connection.commit()
        return {"ok": True, "endpoint": endpoint}

    def delete_subscription(self, endpoint: str) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            cursor = connection.execute("DELETE FROM device_subscriptions WHERE endpoint = ?", (endpoint,))
            connection.commit()
        return {"ok": True, "removed": cursor.rowcount}

    def get_subscription(self, endpoint: str) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT endpoint, p256dh, auth, participant_id, created_at
                FROM device_subscriptions
                WHERE endpoint = ?
                """,
                (endpoint,),
            ).fetchone()
        return dict(row) if row else None

    def subscriptions(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT endpoint, p256dh, auth, participant_id, created_at
                FROM device_subscriptions
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def subscription_count(self, participant_id: str | None = None) -> int:
        with closing(self.connect()) as connection:
            if participant_id:
                row = connection.execute(
                    "SELECT COUNT(*) AS total FROM device_subscriptions WHERE participant_id = ?",
                    (participant_id,),
                ).fetchone()
            else:
                row = connection.execute("SELECT COUNT(*) AS total FROM device_subscriptions").fetchone()
        return int(row["total"]) if row else 0

    def upsert_entry(
        self,
        walk_date: str,
        participant_id: str,
        source: str = "manual",
        notes: str | None = None,
        weather_summary: str | None = None,
        temperature_c: float | None = None,
        pain_index: float | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        previous_entry = self.get_entry(walk_date)
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO walk_entries (
                    walk_date, participant_id, source, notes, weather_summary, temperature_c, pain_index, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(walk_date) DO UPDATE SET
                    participant_id=excluded.participant_id,
                    source=excluded.source,
                    notes=excluded.notes,
                    weather_summary=COALESCE(excluded.weather_summary, walk_entries.weather_summary),
                    temperature_c=COALESCE(excluded.temperature_c, walk_entries.temperature_c),
                    pain_index=COALESCE(excluded.pain_index, walk_entries.pain_index),
                    updated_at=excluded.updated_at
                """,
                (walk_date, participant_id, source, notes, weather_summary, temperature_c, pain_index, now, now),
            )
            connection.commit()
        current_entry = self.get_entry(walk_date)
        if actor and (
            previous_entry is None
            or previous_entry.get("participant_id") != current_entry.get("participant_id")
            or previous_entry.get("source") != current_entry.get("source")
        ):
            self.append_activity(
                actor=actor,
                walk_date=walk_date,
                action="set",
                before=previous_entry,
                after=current_entry,
            )
        return {"ok": True, "walk_date": walk_date, "participant_id": participant_id, "source": source}

    def clear_entry(self, walk_date: str, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        previous_entry = self.get_entry(walk_date)
        with closing(self.connect()) as connection:
            connection.execute("DELETE FROM walk_entries WHERE walk_date = ?", (walk_date,))
            connection.commit()
        if actor and previous_entry is not None:
            self.append_activity(
                actor=actor,
                walk_date=walk_date,
                action="clear",
                before=previous_entry,
                after=None,
            )
        return {"ok": True, "walk_date": walk_date}

    def bulk_plan(
        self,
        start_date: str,
        end_date: str,
        participant_id: str,
        notes: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = parse_date(start_date)
        end = parse_date(end_date)
        if end < start:
            raise ValueError("End date must be on or after start date.")

        current = start
        count = 0
        while current <= end:
            self.upsert_entry(current.isoformat(), participant_id, source="planned", notes=notes, actor=actor)
            current += timedelta(days=1)
            count += 1
        return {"ok": True, "planned_days": count, "participant_id": participant_id}

    def assign_dates(
        self,
        dates: list[str],
        participant_id: str,
        notes: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assigned = 0
        for walk_date in sorted(set(dates)):
            normalized = parse_date(walk_date).isoformat()
            source = "planned" if normalized > date.today().isoformat() else "manual"
            self.upsert_entry(normalized, participant_id, source=source, notes=notes, actor=actor)
            assigned += 1
        return {"ok": True, "assigned_days": assigned, "participant_id": participant_id}

    def import_csv(self, csv_text: str, participant_aliases: dict[str, str]) -> dict[str, Any]:
        import csv
        import io

        cleaned = csv_text.strip()
        if not cleaned:
            raise ValueError("CSV content is empty.")

        delimiter = detect_delimiter(cleaned)
        reader = csv.DictReader(io.StringIO(cleaned), delimiter=delimiter)
        normalized_headers = {header.lower().strip(): header for header in (reader.fieldnames or [])}

        date_key = next((normalized_headers[key] for key in ("date", "day", "walk_date") if key in normalized_headers), None)
        owner_key = next(
            (normalized_headers[key] for key in ("owner", "walker", "person", "who", "taken_by") if key in normalized_headers),
            None,
        )
        participant_columns = {
            original_header: participant_aliases[normalized_header]
            for normalized_header, original_header in normalized_headers.items()
            if normalized_header in participant_aliases
        }

        if not date_key:
            raise ValueError("CSV must include a date column.")
        if not owner_key and not participant_columns:
            raise ValueError("CSV must include a walker column or one column per participant.")

        imported = 0
        skipped = 0
        errors: list[str] = []
        for index, row in enumerate(reader, start=2):
            raw_date = (row.get(date_key) or "").strip()
            if not raw_date:
                skipped += 1
                continue

            try:
                normalized_date = parse_date(raw_date).isoformat()
            except ValueError:
                skipped += 1
                continue

            participant_id = None
            if owner_key:
                raw_owner = (row.get(owner_key) or "").strip().lower()
                if not raw_owner:
                    skipped += 1
                    continue
                participant_id = participant_aliases.get(raw_owner)
                if not participant_id:
                    errors.append(f"Line {index}: unknown walker '{row.get(owner_key)}'")
                    continue
            else:
                marked_participants = [
                    participant_id
                    for column_name, participant_id in participant_columns.items()
                    if is_marked(row.get(column_name))
                ]
                if not marked_participants:
                    skipped += 1
                    continue
                unique_participants = sorted(set(marked_participants))
                if len(unique_participants) > 1:
                    errors.append(f"Line {index}: multiple walkers marked for {normalized_date}")
                    continue
                participant_id = unique_participants[0]

            self.upsert_entry(normalized_date, participant_id, source="imported")
            imported += 1

        return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors}

    def reminder_status(self, requested_date: str | None = None) -> dict[str, Any]:
        target_date = requested_date or date.today().isoformat()
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT walk_date, participant_id, source FROM walk_entries WHERE walk_date = ?",
                (target_date,),
            ).fetchone()

        reminder_needed = row is None
        return {
            "date": target_date,
            "reminder_needed": reminder_needed,
            "reason": "no_walk_logged" if reminder_needed else "already_planned_or_logged",
            "entry": dict(row) if row else None,
        }

    def import_google_sheet(self, sheet_url: str, gid: str = "0") -> dict[str, Any]:
        export_url = google_sheet_export_url(sheet_url, gid=gid)
        with urlopen(export_url, timeout=20) as response:
            csv_text = response.read().decode("utf-8-sig")
        aliases = {
            "frank": "frank",
            "f": "frank",
            "kurt": "kurt",
            "k": "kurt",
        }
        result = self.import_csv(csv_text, aliases)
        result["source_url"] = export_url
        return result


STORE = DogWalkStore(DB_PATH)


class DogWalkHandler(BaseHTTPRequestHandler):
    server_version = "DogWalkTracker/0.1"

    def participant_name(self, participant_id: str | None) -> str:
        participant = next((item for item in PARTICIPANTS if item["id"] == participant_id), None)
        return participant["display_name"] if participant else "Unknown"

    def snapshot_entries(self, dates: list[str]) -> dict[str, dict[str, Any] | None]:
        return {walk_date: STORE.get_entry(walk_date) for walk_date in dates}

    def describe_change_batch(
        self,
        *,
        actor: dict[str, Any],
        before_map: dict[str, dict[str, Any] | None],
        after_map: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        changed_dates = [
            walk_date
            for walk_date in sorted(before_map.keys())
            if (before_map.get(walk_date) or {}).get("participant_id") != (after_map.get(walk_date) or {}).get("participant_id")
            or (before_map.get(walk_date) or {}).get("source") != (after_map.get(walk_date) or {}).get("source")
        ]
        if not changed_dates:
            return None

        additions = [
            walk_date
            for walk_date in changed_dates
            if before_map.get(walk_date) is None and after_map.get(walk_date) is not None
        ]
        removals = [
            walk_date
            for walk_date in changed_dates
            if before_map.get(walk_date) is not None and after_map.get(walk_date) is None
        ]
        swaps = [
            walk_date
            for walk_date in changed_dates
            if before_map.get(walk_date) is not None and after_map.get(walk_date) is not None
        ]

        title = f"{actor['name']} updated Chewie Walk Tracker"

        if additions and not removals and not swaps:
            after_ids = {(after_map[walk_date] or {}).get("participant_id") for walk_date in additions}
            if len(after_ids) == 1:
                participant_name = self.participant_name(next(iter(after_ids)))
                body = f"Added {summarize_dates(additions)} for {participant_name}."
            else:
                body = f"Added {summarize_dates(additions)}."
            return {"title": title, "body": body, "dates": changed_dates}

        if removals and not additions and not swaps:
            before_ids = {(before_map[walk_date] or {}).get("participant_id") for walk_date in removals}
            if len(before_ids) == 1:
                participant_name = self.participant_name(next(iter(before_ids)))
                body = f"Removed {summarize_dates(removals)} from {participant_name}."
            else:
                body = f"Removed {summarize_dates(removals)}."
            return {"title": title, "body": body, "dates": changed_dates}

        if swaps and not additions and not removals:
            before_ids = {(before_map[walk_date] or {}).get("participant_id") for walk_date in swaps}
            after_ids = {(after_map[walk_date] or {}).get("participant_id") for walk_date in swaps}
            if len(before_ids) == 1 and len(after_ids) == 1:
                before_name = self.participant_name(next(iter(before_ids)))
                after_name = self.participant_name(next(iter(after_ids)))
                body = f"Changed {summarize_dates(swaps)} from {before_name} to {after_name}."
            else:
                body = f"Updated {summarize_dates(swaps)}."
            return {"title": title, "body": body, "dates": changed_dates}

        body = f"Updated {summarize_dates(changed_dates)}."
        return {"title": title, "body": body, "dates": changed_dates}

    def notify_subscribers_of_changes(
        self,
        *,
        actor: dict[str, Any],
        before_map: dict[str, dict[str, Any] | None],
        after_map: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        summary = self.describe_change_batch(actor=actor, before_map=before_map, after_map=after_map)
        if not summary:
            return None

        subscriptions = STORE.subscriptions()
        sent = 0
        failed = 0
        failures: list[dict[str, Any]] = []
        for subscription in subscriptions:
            try:
                self.send_push_notification(
                    endpoint=subscription["endpoint"],
                    title=summary["title"],
                    body=summary["body"],
                    tag="chewie-activity",
                    url="/?source=notification",
                )
                sent += 1
            except ValueError as exc:
                failed += 1
                failures.append(
                    {
                        "endpoint": subscription["endpoint"],
                        "participant_id": subscription.get("participant_id"),
                        "error": str(exc),
                    }
                )

        debug_payload = {
            "timestamp": utcnow_iso(),
            "type": "activity_notification",
            "actor": actor,
            "summary": summary,
            "subscription_total": len(subscriptions),
            "sent": sent,
            "failed": failed,
            "failures": failures,
        }
        STORE.append_push_debug(debug_payload)

        return {
            "ok": True,
            "summary": summary,
            "sent": sent,
            "failed": failed,
        }

    def request_debug_snapshot(
        self,
        *,
        payload: dict[str, Any] | None,
        resolved_actor: dict[str, Any],
        action: str,
        target_dates: list[str] | None = None,
    ) -> dict[str, Any]:
        cf_header_email = (self.headers.get("Cf-Access-Authenticated-User-Email") or "").strip().lower() or None
        jwt_header = self.headers.get("Cf-Access-Jwt-Assertion")
        cookie_header = self.headers.get("Cookie")
        cookie_token = cookie_value(cookie_header, "CF_Authorization")
        actor_probe = (payload or {}).get("actor_probe")
        app_probe = (payload or {}).get("app_probe")
        return {
            "timestamp": utcnow_iso(),
            "action": action,
            "path": self.path,
            "method": self.command,
            "target_dates": target_dates or [],
            "claimed_actor_email": (payload or {}).get("actor_email"),
            "actor_probe": actor_probe if isinstance(actor_probe, dict) else None,
            "app_probe": app_probe if isinstance(app_probe, dict) else None,
            "resolved_actor": resolved_actor,
            "server_app": {
                "version": APP_VERSION,
                "mode": APP_MODE,
            },
            "headers": {
                "host": self.headers.get("Host"),
                "origin": self.headers.get("Origin"),
                "referer": self.headers.get("Referer"),
                "user_agent": self.headers.get("User-Agent"),
                "cf_connecting_ip": self.headers.get("CF-Connecting-IP"),
                "cf_ray": self.headers.get("CF-Ray"),
                "cf_access_authenticated_user_email": cf_header_email,
                "cf_access_jwt_assertion_present": bool(jwt_header),
                "cf_access_jwt_assertion_email": jwt_email(jwt_header),
                "cf_authorization_cookie_present": bool(cookie_token),
                "cf_authorization_cookie_email": jwt_email(cookie_token),
            },
        }

    def request_actor(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        claimed_email = canonical_email((payload or {}).get("actor_email"))
        actor = ACTOR_EMAILS.get(claimed_email)
        if actor:
            return {
                "id": actor["id"],
                "name": actor["name"],
                "email": claimed_email,
                "source": "client_claim",
            }

        email = canonical_email(self.headers.get("Cf-Access-Authenticated-User-Email"))
        email_source = "cloudflare_access_header"
        if not email:
            email = jwt_email(self.headers.get("Cf-Access-Jwt-Assertion"))
            email_source = "cloudflare_access_jwt"
        if not email:
            email = jwt_email(cookie_value(self.headers.get("Cookie"), "CF_Authorization"))
            email_source = "cloudflare_access_cookie"
        actor = ACTOR_EMAILS.get(email)
        if actor:
            return {
                "id": actor["id"],
                "name": actor["name"],
                "email": email,
                "source": email_source,
            }
        return {
            "id": "frank",
            "name": "Frank",
            "email": None,
            "source": "lan_fallback",
        }

    def bootstrap_payload(
        self,
        month_key: str,
        range_start: str | None = None,
        range_end: str | None = None,
    ) -> dict[str, Any]:
        payload = STORE.get_month_payload(month_key, range_start=range_start, range_end=range_end)
        payload["app"] = {
            "version": APP_VERSION,
            "mode": APP_MODE,
        }
        payload["actor"] = self.request_actor()
        return payload

    def push_status_payload(self) -> dict[str, Any]:
        actor = self.request_actor()
        material = vapid_material()
        return {
            "ok": True,
            "app": {
                "version": APP_VERSION,
                "mode": APP_MODE,
            },
            "actor": actor,
            "vapid_public_key": material["public_key"],
            "subscriptions": {
                "total": STORE.subscription_count(),
                "actor": STORE.subscription_count(actor["id"]) if actor.get("id") else 0,
            },
        }

    def send_push_notification(
        self,
        *,
        endpoint: str,
        title: str,
        body: str,
        tag: str,
        url: str = "/?source=notification",
    ) -> None:
        subscription = STORE.get_subscription(endpoint)
        if not subscription:
            raise ValueError("Subscription not found.")

        material = vapid_material()
        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "tag": tag,
                "url": url,
                "icon": f"/icon-192.png?v={APP_VERSION}",
                "badge": f"/icon-192.png?v={APP_VERSION}",
            },
            ensure_ascii=True,
        )

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {
                        "p256dh": subscription["p256dh"],
                        "auth": subscription["auth"],
                    },
                },
                data=payload,
                vapid_private_key=material["private_key_path"],
                vapid_claims={"sub": material["subject"]},
                ttl=300,
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                STORE.delete_subscription(endpoint)
            error_message = f"Could not send push notification ({status_code or 'unknown'})."
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    response_body = response.text
                except Exception:
                    response_body = None
                if response_body:
                    error_message = f"{error_message} {response_body}"
            raise ValueError(error_message) from exc

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            json_response(self, {"ok": True, "service": "dog-walk-tracker", "timestamp": utcnow_iso()})
            return

        if path == "/api/bootstrap":
            month_key = query.get("month", [date.today().strftime("%Y-%m")])[0]
            range_start = query.get("range_start", [None])[0]
            range_end = query.get("range_end", [None])[0]
            json_response(self, self.bootstrap_payload(month_key, range_start=range_start, range_end=range_end))
            return

        if path == "/api/admin/diagnostics":
            json_response(self, STORE.diagnostic_payload())
            return

        if path == "/api/activity":
            limit = int(query.get("limit", ["80"])[0])
            json_response(self, {"ok": True, "items": STORE.recent_activity(limit=limit)})
            return

        if path == "/api/admin/write-debug":
            limit = int(query.get("limit", ["80"])[0])
            json_response(self, {"ok": True, "items": STORE.recent_write_debug(limit=limit)})
            return

        if path == "/api/admin/push-debug":
            limit = int(query.get("limit", ["80"])[0])
            json_response(self, {"ok": True, "items": STORE.recent_push_debug(limit=limit)})
            return

        if path == "/api/stats":
            range_key = query.get("range", ["90"])[0]
            json_response(self, STORE.stats_payload(range_key=range_key))
            return

        if path == "/api/push/status":
            json_response(self, self.push_status_payload())
            return

        if path == "/api/reminders/pending":
            target_date = query.get("date", [None])[0]
            json_response(self, STORE.reminder_status(target_date))
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/admin/upload-sqlite":
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length) if content_length else b""
                json_response(self, STORE.replace_database_bytes(body))
                return

            payload = read_json_body(self)
            if path == "/api/entries":
                walk_date = payload["walk_date"]
                participant_id = payload["participant_id"]
                notes = payload.get("notes")
                source = payload.get("source", "manual")
                actor = self.request_actor(payload)
                target_dates = [walk_date]
                before_map = self.snapshot_entries(target_dates)
                STORE.append_write_debug(
                    self.request_debug_snapshot(
                        payload=payload,
                        resolved_actor=actor,
                        action="set_single",
                        target_dates=target_dates,
                    )
                )
                result = STORE.upsert_entry(
                    walk_date,
                    participant_id,
                    source=source,
                    notes=notes,
                    actor=actor,
                )
                after_map = self.snapshot_entries(target_dates)
                notification = self.notify_subscribers_of_changes(
                    actor=actor,
                    before_map=before_map,
                    after_map=after_map,
                )
                response_payload = {**result, "notification": notification}
                json_response(
                    self,
                    response_payload,
                )
                return

            if path == "/api/entries/bulk-plan":
                actor = self.request_actor(payload)
                start_date = payload["start_date"]
                end_date = payload["end_date"]
                target_dates = daterange_dates(start_date, end_date)
                before_map = self.snapshot_entries(target_dates)
                STORE.append_write_debug(
                    self.request_debug_snapshot(
                        payload=payload,
                        resolved_actor=actor,
                        action="bulk_plan",
                        target_dates=target_dates,
                    )
                )
                result = STORE.bulk_plan(
                    start_date=start_date,
                    end_date=end_date,
                    participant_id=payload["participant_id"],
                    notes=payload.get("notes"),
                    actor=actor,
                )
                after_map = self.snapshot_entries(target_dates)
                notification = self.notify_subscribers_of_changes(
                    actor=actor,
                    before_map=before_map,
                    after_map=after_map,
                )
                json_response(
                    self,
                    {**result, "notification": notification},
                )
                return

            if path == "/api/entries/assign-dates":
                actor = self.request_actor(payload)
                target_dates = [parse_date(item).isoformat() for item in list(payload.get("dates") or [])]
                before_map = self.snapshot_entries(target_dates)
                STORE.append_write_debug(
                    self.request_debug_snapshot(
                        payload=payload,
                        resolved_actor=actor,
                        action="assign_dates",
                        target_dates=target_dates,
                    )
                )
                result = STORE.assign_dates(
                    dates=payload["dates"],
                    participant_id=payload["participant_id"],
                    notes=payload.get("notes"),
                    actor=actor,
                )
                after_map = self.snapshot_entries(target_dates)
                notification = self.notify_subscribers_of_changes(
                    actor=actor,
                    before_map=before_map,
                    after_map=after_map,
                )
                json_response(
                    self,
                    {**result, "notification": notification},
                )
                return

            if path == "/api/import/csv":
                aliases = {
                    "frank": "frank",
                    "f": "frank",
                    "kurt": "kurt",
                    "k": "kurt",
                }
                json_response(self, STORE.import_csv(payload.get("csv_text", ""), aliases))
                return

            if path == "/api/import/google-sheet":
                json_response(
                    self,
                    STORE.import_google_sheet(payload["sheet_url"], gid=payload.get("gid", "0")),
                )
                return

            if path == "/api/admin/correct-activity":
                json_response(self, STORE.correct_activity_entries(payload.get("corrections") or []))
                return

            if path == "/api/push/subscribe":
                actor = self.request_actor(payload)
                subscription = payload.get("subscription") or {}
                keys = subscription.get("keys") or {}
                endpoint = str(subscription.get("endpoint") or "").strip()
                p256dh = str(keys.get("p256dh") or "").strip()
                auth = str(keys.get("auth") or "").strip()
                if not endpoint or not p256dh or not auth:
                    raise ValueError("Push subscription is incomplete.")
                json_response(
                    self,
                    STORE.upsert_subscription(
                        participant_id=actor["id"],
                        endpoint=endpoint,
                        p256dh=p256dh,
                        auth=auth,
                    ),
                )
                return

            if path == "/api/push/unsubscribe":
                endpoint = str((payload.get("subscription") or {}).get("endpoint") or payload.get("endpoint") or "").strip()
                if not endpoint:
                    raise ValueError("Subscription endpoint is required.")
                json_response(self, STORE.delete_subscription(endpoint))
                return

            if path == "/api/push/test":
                actor = self.request_actor(payload)
                endpoint = str((payload.get("subscription") or {}).get("endpoint") or payload.get("endpoint") or "").strip()
                if not endpoint:
                    raise ValueError("Subscription endpoint is required.")
                self.send_push_notification(
                    endpoint=endpoint,
                    title="Chewie Walk Tracker",
                    body=f"{actor['name']} sent a test notification for this device.",
                    tag="chewie-test",
                )
                json_response(self, {"ok": True, "sent": 1})
                return
        except KeyError as exc:
            json_response(self, {"ok": False, "error": f"Missing field: {exc.args[0]}"}, status=400)
            return
        except ValueError as exc:
            json_response(self, {"ok": False, "error": str(exc)}, status=400)
            return
        except json.JSONDecodeError:
            json_response(self, {"ok": False, "error": "Invalid JSON body."}, status=400)
            return

        json_response(self, {"ok": False, "error": "Not found."}, status=404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/entries/"):
            walk_date = parsed.path.rsplit("/", 1)[-1]
            try:
                parse_date(walk_date)
            except ValueError:
                json_response(self, {"ok": False, "error": "Invalid date."}, status=400)
                return
            payload = {}
            if self.headers.get("Content-Length"):
                try:
                    payload = read_json_body(self)
                except json.JSONDecodeError:
                    json_response(self, {"ok": False, "error": "Invalid JSON body."}, status=400)
                    return
            actor = self.request_actor(payload)
            target_dates = [walk_date]
            before_map = self.snapshot_entries(target_dates)
            STORE.append_write_debug(
                self.request_debug_snapshot(
                    payload=payload,
                    resolved_actor=actor,
                    action="clear",
                    target_dates=target_dates,
                )
            )
            result = STORE.clear_entry(walk_date, actor=actor)
            after_map = self.snapshot_entries(target_dates)
            notification = self.notify_subscribers_of_changes(
                actor=actor,
                before_map=before_map,
                after_map=after_map,
            )
            json_response(self, {**result, "notification": notification})
            return

        json_response(self, {"ok": False, "error": "Not found."}, status=404)

    def serve_static(self, path: str) -> None:
        if path == "/":
            target = STATIC_DIR / "index.html"
        else:
            target = STATIC_DIR / path.lstrip("/")

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found.")
            return

        mime_type, _ = mimetypes.guess_type(target.name)
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if path == "/" or target.name in {"index.html", "sw.js"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        elif target.suffix in {".js", ".css", ".json", ".webmanifest", ".png", ".jpg", ".svg"}:
            self.send_header("Cache-Control", "no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def run() -> None:
    host = os.environ.get("DOG_WALK_HOST", "0.0.0.0")
    port = int(os.environ.get("DOG_WALK_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), DogWalkHandler)
    print(f"Dog walk tracker running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
