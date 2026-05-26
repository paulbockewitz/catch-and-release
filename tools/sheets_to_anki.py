#!/usr/bin/env python3
"""
sheets_to_anki.py

Reads rows from a Google Sheet and creates Anki flashcards via the AnkiWeb CLI.
After each successful card creation, writes a checkmark to a "done" column so
re-runs safely skip already-processed rows.

Column layout and all settings are driven by .env — nothing is hardcoded.

Required .env variables:
    GOOGLE_SHEET_ID       — Spreadsheet ID from the sheet URL (/d/<ID>/edit)
    ANKI_DECK             — Deck name or ID (run: ankiweb-pp-cli decks list)
    ANKIWEB_CLI_PATH      — Full path to the ankiweb-pp-cli binary

Optional .env variables (all have defaults):
    GOOGLE_SHEET_TAB      — Tab name (default: Sheet1)
    ANKI_HEADER_ROW       — Rows to skip at top: "1" skips row 1, "1-2" skips
                            rows 1 and 2, "0" means no header (default: 1)
    ANKI_FRONT_COL        — Column letter for card front (default: A)
    ANKI_BACK_COL         — Column letter for card back  (default: B)
    ANKI_DONE_COL         — Column letter for checkmark  (default: D)
    ANKI_DONE_MARKER      — Value written on success     (default: ✓)
    ANKI_NOTETYPE         — Note type name or ID         (default: Basic (and reversed card))
    ANKI_TAGS             — Space-separated tags to attach to all cards (default: none)
    LOG_DIR               — Log output directory, relative to project root (default: .tmp)

Usage:
    python tools/sheets_to_anki.py
    python tools/sheets_to_anki.py --dry-run
    python tools/sheets_to_anki.py --sheet-id <ID> --deck "My Deck"
    python tools/sheets_to_anki.py --help
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openpyxl.utils import column_index_from_string

# Read+write scope required — we write the checkmark back to the sheet
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Ensure Unicode characters (arrows, accented letters, ✓) print correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_env(key: str, default: str = None) -> str:
    """Get an env var; exit with a helpful error if required and missing."""
    val = os.getenv(key, default)
    if val is None:
        print(f"ERROR: {key} is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)
    return val


def get_sheets_service():
    """
    Authenticate with the Google Sheets API and return a service object.

    On first run, opens a browser tab for the user to authorize access and
    saves token.json. Subsequent runs use the saved token, refreshed automatically.

    Paths are read from GOOGLE_CREDENTIALS_FILE and GOOGLE_TOKEN_FILE in .env.
    Relative paths are resolved against the project root.

    NOTE: Uses read+write scope. If you previously ran with readonly scope,
    delete token.json and re-run to re-authorize.
    """
    creds = None

    creds_raw = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    token_raw = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    _cp = Path(creds_raw)
    _tp = Path(token_raw)
    creds_path = _cp if _cp.is_absolute() else PROJECT_ROOT / creds_raw
    token_path = _tp if _tp.is_absolute() else PROJECT_ROOT / token_raw

    if not creds_path.exists():
        print(f"ERROR: credentials file not found at {creds_path}", file=sys.stderr)
        print("  Download it from: https://console.cloud.google.com/apis/credentials", file=sys.stderr)
        print("  Create Credentials → OAuth client ID → Desktop app → Download JSON", file=sys.stderr)
        print(f"  Then set GOOGLE_CREDENTIALS_FILE in .env (current value: {creds_raw!r})", file=sys.stderr)
        sys.exit(1)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("  Opening browser for Google authorization (one-time only)...")
            print("  NOTE: This requires read+write access to update the checkmark column.")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"  Auth token saved to {token_path.name}")

    return build("sheets", "v4", credentials=creds)


def read_sheet(service, sheet_id: str, tab: str) -> list:
    """
    Read all rows from the sheet tab. Returns a list of row lists (strings).
    Missing trailing cells in a row are NOT included by the Sheets API — callers
    must handle short rows gracefully.
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab}'",
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        return result.get("values", [])
    except Exception as exc:
        print(f"ERROR reading sheet '{tab}': {exc}", file=sys.stderr)
        sys.exit(1)


def write_done_marker(service, sheet_id: str, tab: str, sheet_row: int, done_col: str, marker: str):
    """
    Write the done marker to a single cell.
    sheet_row is the 1-based row number in the spreadsheet (including header rows).
    """
    cell_range = f"'{tab}'!{done_col}{sheet_row}"
    body = {"values": [[marker]]}
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=cell_range,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def run_cmd(cmd: list) -> tuple:
    """Run a subprocess command. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", f"Command not found: {cmd[0]} — {exc}"


def add_note(ankiweb_bin: str, deck: str, notetype: str, front: str, back: str, tags: str, dry_run: bool) -> tuple:
    """
    Add a note via the AnkiWeb CLI. Returns (success: bool, message: str).
    --idempotent means "already exists" is treated as success, preventing duplicates.
    """
    cmd = [
        ankiweb_bin, "notes", "add",
        front, back,
        "--deck", deck,
        "--type", notetype,
        "--idempotent",
        "--yes",
        "--no-input",
    ]
    if tags:
        cmd += ["--tags", tags]

    if dry_run:
        return True, "[dry-run]"

    code, stdout, stderr = run_cmd(cmd)
    if code != 0:
        return False, (stderr or stdout or f"exit code {code}")
    return True, stdout


def write_log(log_path: Path, sheet_id: str, tab: str, run_start: datetime,
              added: list, skipped: list, errors: list):
    """Write a human-readable run log to .tmp/."""
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Run: {run_start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Sheet: {sheet_id} / {tab}\n")
        f.write("-" * 60 + "\n")
        for front, back, row_num in added:
            f.write(f"ADDED:   {front} → {back}  [row {row_num}]\n")
        for front, row_num, reason in skipped:
            f.write(f"SKIPPED: {front}  [row {row_num}] ({reason})\n")
        for front, back, row_num, err in errors:
            f.write(f"ERROR:   {front} → {back}  [row {row_num}] — {err}\n")
        f.write("-" * 60 + "\n")
        f.write(f"Summary: {len(added)} added, {len(skipped)} skipped, {len(errors)} error(s)\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sync rows from a Google Sheet to Anki flashcards.\n"
            "Creates 'Basic (and reversed card)' notes via the AnkiWeb CLI.\n"
            "Writes a checkmark to the done column after each successful creation.\n"
            "Re-runs safely skip already-marked rows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be processed; no Anki calls, no checkmarks written.",
    )
    parser.add_argument("--sheet-id", help="Override GOOGLE_SHEET_ID from .env.")
    parser.add_argument("--tab",      help="Override GOOGLE_SHEET_TAB from .env.")
    parser.add_argument("--deck",     help="Override ANKI_DECK from .env.")
    args = parser.parse_args()

    run_start = datetime.now()

    sheet_id    = args.sheet_id or get_env("GOOGLE_SHEET_ID")
    tab         = args.tab      or get_env("GOOGLE_SHEET_TAB", "Sheet1")
    deck        = args.deck     or get_env("ANKI_DECK")
    notetype    = get_env("ANKI_NOTETYPE", "Basic (and reversed card)")
    tags        = os.getenv("ANKI_TAGS", "")
    done_marker = get_env("ANKI_DONE_MARKER", "✓")
    ankiweb_bin = get_env("ANKIWEB_CLI_PATH", r"C:\Users\paulb\printing-press\library\ankiweb\ankiweb-pp-cli.exe")
    log_dir_rel = get_env("LOG_DIR", ".tmp")

    _header_raw = get_env("ANKI_HEADER_ROW", "1")
    try:
        header_row = int(_header_raw.split("-")[-1]) if "-" in _header_raw else int(_header_raw)
    except ValueError:
        print(f"ERROR: ANKI_HEADER_ROW={_header_raw!r} is not a valid number or range (e.g. '1' or '1-2').", file=sys.stderr)
        sys.exit(1)

    front_col = get_env("ANKI_FRONT_COL", "A")
    back_col  = get_env("ANKI_BACK_COL",  "B")
    done_col  = get_env("ANKI_DONE_COL",  "D")

    try:
        front_idx = column_index_from_string(front_col) - 1
        back_idx  = column_index_from_string(back_col)  - 1
        done_idx  = column_index_from_string(done_col)  - 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    log_dir = PROJECT_ROOT / log_dir_rel
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"sheets_to_anki_{run_start.strftime('%Y%m%d_%H%M%S')}.txt"

    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN — no Anki cards will be created")
        print("  No checkmarks will be written to the sheet")
        print("=" * 60)
        print()

    print("Connecting to Google Sheets...")
    service = get_sheets_service()
    print("  Connected.")

    print(f"Reading sheet: {sheet_id!r} / tab: {tab!r} ...")
    rows = read_sheet(service, sheet_id, tab)
    print(f"  {len(rows)} total rows ({len(rows) - header_row} data rows after header).")
    print()

    added:   list = []
    skipped: list = []
    errors:  list = []

    for i, row in enumerate(rows[header_row:], start=header_row):
        sheet_row_num = i + 1

        front = row[front_idx].strip() if len(row) > front_idx else ""
        back  = row[back_idx].strip()  if len(row) > back_idx  else ""
        done  = row[done_idx].strip()  if len(row) > done_idx  else ""

        if not front or not back:
            skipped.append((front or "(blank)", sheet_row_num, "blank front or back"))
            print(f"  SKIP  row {sheet_row_num} — blank front or back")
            continue

        if done:
            skipped.append((front, sheet_row_num, "already done"))
            print(f"  SKIP  row {sheet_row_num} — already done  ({front})")
            continue

        success, msg = add_note(ankiweb_bin, deck, notetype, front, back, tags, args.dry_run)

        if success:
            added.append((front, back, sheet_row_num))
            if args.dry_run:
                print(f"  WOULD ADD  row {sheet_row_num}: {front} → {back}")
            else:
                try:
                    write_done_marker(service, sheet_id, tab, sheet_row_num, done_col, done_marker)
                    print(f"  ADDED  row {sheet_row_num}: {front} → {back}")
                except Exception as exc:
                    errors.append((front, back, sheet_row_num, f"card added but checkmark failed: {exc}"))
                    print(f"  WARN   row {sheet_row_num}: card added, but checkmark write failed — {exc}", file=sys.stderr)
        else:
            errors.append((front, back, sheet_row_num, msg))
            print(f"  ERROR  row {sheet_row_num}: {front} → {back} — {msg}", file=sys.stderr)

    print()
    print("=" * 60)
    verb = "Would add" if args.dry_run else "Added"
    print(f"{'DRY RUN ' if args.dry_run else ''}Complete — {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  {verb}:    {len(added)} note(s)  (→ {len(added) * 2} Anki cards via reversed notetype)")
    print(f"  Skipped:  {len(skipped)}")
    print(f"  Errors:   {len(errors)}")

    if not args.dry_run:
        write_log(log_path, sheet_id, tab, run_start, added, skipped, errors)
        print(f"\nLog written to: {log_path.relative_to(PROJECT_ROOT)}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
