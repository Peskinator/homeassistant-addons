from __future__ import annotations

import json
import mimetypes
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.environ.get("DOG_WALK_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "dog_walks.sqlite3"
SEED_DB_PATH = BASE_DIR / "data" / "dog_walks.sqlite3"
DEFAULT_PORT = 8420
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


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length).decode("utf-8") if content_length else "{}"
    return json.loads(raw or "{}")


class DogWalkStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path != SEED_DB_PATH and not self.db_path.exists() and SEED_DB_PATH.exists():
            shutil.copy2(SEED_DB_PATH, self.db_path)
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

    def participants(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT id, display_name, short_name, color, accent, photo FROM participants ORDER BY display_name"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_month_payload(self, month_key: str) -> dict[str, Any]:
        month_start, next_month = month_bounds(month_key)
        with closing(self.connect()) as connection:
            month_rows = connection.execute(
                """
                SELECT walk_date, participant_id, source, notes, weather_summary, temperature_c, pain_index
                FROM walk_entries
                WHERE walk_date >= ? AND walk_date < ?
                ORDER BY walk_date
                """,
                (month_start.isoformat(), next_month.isoformat()),
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

    def upsert_entry(
        self,
        walk_date: str,
        participant_id: str,
        source: str = "manual",
        notes: str | None = None,
        weather_summary: str | None = None,
        temperature_c: float | None = None,
        pain_index: float | None = None,
    ) -> dict[str, Any]:
        now = utcnow_iso()
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
        return {"ok": True, "walk_date": walk_date, "participant_id": participant_id, "source": source}

    def clear_entry(self, walk_date: str) -> dict[str, Any]:
        with closing(self.connect()) as connection:
            connection.execute("DELETE FROM walk_entries WHERE walk_date = ?", (walk_date,))
            connection.commit()
        return {"ok": True, "walk_date": walk_date}

    def bulk_plan(
        self,
        start_date: str,
        end_date: str,
        participant_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        start = parse_date(start_date)
        end = parse_date(end_date)
        if end < start:
            raise ValueError("End date must be on or after start date.")

        current = start
        count = 0
        while current <= end:
            self.upsert_entry(current.isoformat(), participant_id, source="planned", notes=notes)
            current += timedelta(days=1)
            count += 1
        return {"ok": True, "planned_days": count, "participant_id": participant_id}

    def assign_dates(
        self,
        dates: list[str],
        participant_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        assigned = 0
        for walk_date in sorted(set(dates)):
            normalized = parse_date(walk_date).isoformat()
            source = "planned" if normalized > date.today().isoformat() else "manual"
            self.upsert_entry(normalized, participant_id, source=source, notes=notes)
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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            json_response(self, {"ok": True, "service": "dog-walk-tracker", "timestamp": utcnow_iso()})
            return

        if path == "/api/bootstrap":
            month_key = query.get("month", [date.today().strftime("%Y-%m")])[0]
            json_response(self, STORE.get_month_payload(month_key))
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
            payload = read_json_body(self)
            if path == "/api/entries":
                walk_date = payload["walk_date"]
                participant_id = payload["participant_id"]
                notes = payload.get("notes")
                source = payload.get("source", "manual")
                json_response(self, STORE.upsert_entry(walk_date, participant_id, source=source, notes=notes))
                return

            if path == "/api/entries/bulk-plan":
                json_response(
                    self,
                    STORE.bulk_plan(
                        start_date=payload["start_date"],
                        end_date=payload["end_date"],
                        participant_id=payload["participant_id"],
                        notes=payload.get("notes"),
                    ),
                )
                return

            if path == "/api/entries/assign-dates":
                json_response(
                    self,
                    STORE.assign_dates(
                        dates=payload["dates"],
                        participant_id=payload["participant_id"],
                        notes=payload.get("notes"),
                    ),
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
            json_response(self, STORE.clear_entry(walk_date))
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
        if target.suffix in {".js", ".css", ".html", ".json", ".webmanifest"}:
            self.send_header("Cache-Control", "no-cache")
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
