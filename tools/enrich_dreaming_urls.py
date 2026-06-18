#!/usr/bin/env python3
"""
enrich_dreaming_urls.py

For each Spanish vocabulary word in the Google Sheet that doesn't yet have a
Dreaming.com URL, queries the dreaming-pp-cli concordance command and writes
the first matching video URL + hit count to a dedicated sheet column.

Idempotent: rows that already have any value in the URL column are skipped.
Zero-hit words receive "no matches" so they aren't re-queried on future runs.

Required .env variables:
    GOOGLE_SHEET_ID       — Spreadsheet ID from the sheet URL (/d/<ID>/edit)

Optional .env variables (all have defaults):
    GOOGLE_SHEET_TAB      — Tab name (default: Sheet1)
    ANKI_BACK_COL         — Column letter with Spanish words (default: B)
    ANKI_HEADER_ROW       — Rows to skip at top (default: 1)
    DREAMING_URL_COLUMN   — Column letter to write URLs into (default: E)
    DREAMING_CLI_PATH     — Path or name of dreaming-pp-cli binary (default: dreaming-pp-cli)
    DREAMING_LOG_PATH     — Append-mode log file path (default: .tmp/dreaming_enrichment.log)

Usage:
    python tools/enrich_dreaming_urls.py
    python tools/enrich_dreaming_urls.py --dry-run
    python tools/enrich_dreaming_urls.py --help
"""

import argparse
import json
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

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

NO_MATCHES = "no matches"


def get_env(key: str, default: str = None) -> str:
    val = os.getenv(key, default)
    if val is None:
        print(f"ERROR: {key} is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)
    return val


def get_sheets_service():
    creds = None

    creds_raw = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    token_raw = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    creds_path = Path(creds_raw) if Path(creds_raw).is_absolute() else PROJECT_ROOT / creds_raw
    token_path = Path(token_raw) if Path(token_raw).is_absolute() else PROJECT_ROOT / token_raw

    if not creds_path.exists():
        print(f"ERROR: credentials file not found at {creds_path}", file=sys.stderr)
        sys.exit(1)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("  Opening browser for Google authorization (one-time only)...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("sheets", "v4", credentials=creds)


def read_sheet(service, sheet_id: str, tab: str) -> list:
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


def write_cell(service, sheet_id: str, tab: str, sheet_row: int, col: str, value: str):
    cell_range = f"'{tab}'!{col}{sheet_row}"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=cell_range,
        valueInputOption="USER_ENTERED",
        body={"values": [[value]]},
    ).execute()


def run_cmd(cmd: list) -> tuple:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", f"Command not found: {cmd[0]} — {exc}"


def query_concordance(cli_path: str, spanish_word: str) -> tuple:
    """
    Returns (first_url, hit_count, error_message).
    On success: (url_string_or_None, int, None).
    On CLI-not-found: (-1 sentinel via error_message).
    """
    code, stdout, stderr = run_cmd([
        cli_path, "concordance", spanish_word,
        "--json", "--limit", "50",
    ])

    if code == -1:
        return None, 0, stderr

    if code != 0:
        return None, 0, (stderr or stdout or f"exit code {code}")

    if not stdout:
        return None, 0, None

    try:
        hits = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, 0, f"JSON parse error: {exc}"

    if not isinstance(hits, list) or len(hits) == 0:
        return None, 0, None

    first = hits[0]
    url = first.get("url") or first.get("URL") or first.get("VideoURL") or ""
    return url, len(hits), None


def append_log(log_path: Path, lines: list):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Enrich vocabulary sheet rows with Dreaming.com video URLs.\n"
            "Queries dreaming-pp-cli concordance for each unenriched Spanish word\n"
            "and writes the first matching URL + hit count to a sheet column.\n"
            "Already-enriched rows are skipped (idempotent)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be written; no sheet writes, no log writes.",
    )
    args = parser.parse_args()

    run_start = datetime.now()
    ts = run_start.strftime("%Y-%m-%d %H:%M:%S")

    sheet_id   = get_env("GOOGLE_SHEET_ID")
    tab        = get_env("GOOGLE_SHEET_TAB", "Sheet1")
    back_col   = get_env("ANKI_BACK_COL", "B")
    url_col    = get_env("DREAMING_URL_COLUMN", "E")
    cli_path   = get_env("DREAMING_CLI_PATH", "dreaming-pp-cli")
    log_path   = Path(get_env("DREAMING_LOG_PATH", str(PROJECT_ROOT / ".tmp" / "dreaming_enrichment.log")))

    _header_raw = get_env("ANKI_HEADER_ROW", "1")
    try:
        header_row = int(_header_raw.split("-")[-1]) if "-" in _header_raw else int(_header_raw)
    except ValueError:
        print(f"ERROR: ANKI_HEADER_ROW={_header_raw!r} is not a valid number or range.", file=sys.stderr)
        sys.exit(1)

    try:
        back_idx = column_index_from_string(back_col) - 1
        url_idx  = column_index_from_string(url_col)  - 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Verify CLI is reachable before touching the sheet
    probe_code, _, probe_err = run_cmd([cli_path, "--version"])
    if probe_code == -1:
        print(f"WARNING: dreaming-pp-cli not found at {cli_path!r}. Skipping enrichment.", file=sys.stderr)
        print(f"  Install it or set DREAMING_CLI_PATH in .env.", file=sys.stderr)
        sys.exit(0)

    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN — no sheet writes, no log writes")
        print("=" * 60)
        print()

    print("Connecting to Google Sheets...")
    service = get_sheets_service()
    print("  Connected.")

    print(f"Reading sheet: {sheet_id!r} / tab: {tab!r} ...")
    rows = read_sheet(service, sheet_id, tab)
    data_rows = rows[header_row:]
    print(f"  {len(rows)} total rows ({len(data_rows)} data rows after header).")
    print()

    enriched   = 0
    no_matches = 0
    skipped    = 0
    errors     = 0
    log_lines  = []

    for i, row in enumerate(data_rows, start=header_row):
        sheet_row_num = i + 1

        spanish = row[back_idx].strip() if len(row) > back_idx else ""
        current = row[url_idx].strip()  if len(row) > url_idx  else ""

        if not spanish:
            skipped += 1
            print(f"  SKIP  row {sheet_row_num} — blank Spanish word")
            continue

        if current:
            skipped += 1
            print(f"  SKIP  row {sheet_row_num} — already enriched  ({spanish})")
            continue

        print(f"  QUERY row {sheet_row_num}: {spanish!r} ...")
        url, count, err = query_concordance(cli_path, spanish)

        if err:
            errors += 1
            msg = f"ERROR row {sheet_row_num} ({spanish}): {err}"
            print(f"  {msg}", file=sys.stderr)
            log_lines.append(f"[{ts}] {msg}")
            continue

        if url:
            cell_value = f"{url} ({count} matches)"
            enriched += 1
            if args.dry_run:
                print(f"  WOULD WRITE  row {sheet_row_num}: {cell_value}")
            else:
                write_cell(service, sheet_id, tab, sheet_row_num, url_col, cell_value)
                print(f"  WROTE  row {sheet_row_num}: {cell_value}")
        else:
            cell_value = NO_MATCHES
            no_matches += 1
            if args.dry_run:
                print(f"  WOULD WRITE  row {sheet_row_num}: {NO_MATCHES}")
            else:
                write_cell(service, sheet_id, tab, sheet_row_num, url_col, NO_MATCHES)
                print(f"  WROTE  row {sheet_row_num}: {NO_MATCHES}  ({spanish})")

    print()
    print("=" * 60)
    print(f"{'DRY RUN ' if args.dry_run else ''}Complete — {ts}")
    print(f"  Enriched:   {enriched}")
    print(f"  No matches: {no_matches}")
    print(f"  Skipped:    {skipped}")
    print(f"  Errors:     {errors}")

    if not args.dry_run:
        summary = (
            f"[{ts}] Dreaming URL enrichment: "
            f"{enriched} enriched, {no_matches} no matches, "
            f"{skipped} skipped, {errors} error(s)"
        )
        log_lines.append(summary)
        append_log(log_path, log_lines)
        print(f"\nLog appended to: {log_path}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
