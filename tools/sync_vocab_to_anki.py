#!/usr/bin/env python3
"""
sync_vocab_to_anki.py

Reads vocabulary from a Google Sheet (two tabs) and creates bidirectional
Anki flashcards via the AnkiWeb CLI. Works for any language pair.

The Google Sheet must have two tabs:
  - Target language tab  (col A = word/phrase in language being learned,
                          col B = native language translation)
  - Native language tab  (col A = native language word/phrase,
                          col B = translation in language being learned)

Both single words and multi-word phrases are supported. Uses the
"Basic (and reversed card)" notetype to create 2 cards per entry.

Required .env variables:
    GOOGLE_SHEET_ID       — Spreadsheet ID from the sheet URL
    ANKI_DECK_ID          — Numeric deck ID (run: ankiweb decks list --json)
    ANKI_NOTETYPE_ID      — Notetype ID for "Basic (and reversed card)"
    ANKIWEB_CLI_PATH      — Full path to the ankiweb-pp-cli-pp-cli binary

Optional .env variables:
    TARGET_LANG_SHEET     — Tab name for the target-language sheet (default: Sheet1)
    NATIVE_LANG_SHEET     — Tab name for the native-language sheet  (default: Sheet2)
    LEARNING_LANGUAGE     — Display name used in logs, e.g. "Spanish" (default: target)

Usage:
    python tools/sync_vocab_to_anki.py
    python tools/sync_vocab_to_anki.py --dry-run
    python tools/sync_vocab_to_anki.py --help
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

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Ensure Unicode characters (arrows, accented letters) print correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load .env from project root (one level up from tools/)
load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_env(key: str, default: str = None) -> str:
    """Get a required env var, or exit with a helpful error."""
    val = os.getenv(key, default)
    if val is None:
        print(f"ERROR: {key} is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd: list) -> tuple:
    """
    Run a subprocess command.
    Returns (returncode, stdout, stderr) — all strings.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", f"Command not found: {cmd[0]} — {exc}"


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def get_sheets_service(project_root: Path):
    """
    Authenticate with the Google Sheets API and return a service object.

    On first run, opens a browser tab for the user to authorize access and
    saves token.json next to credentials.json. Subsequent runs use the saved
    token, which is refreshed automatically when it expires.
    """
    creds = None
    token_path = project_root / "token.json"
    creds_path = project_root / "credentials.json"

    if not creds_path.exists():
        print(f"ERROR: credentials.json not found at {creds_path}", file=sys.stderr)
        print("  Download it from: https://console.cloud.google.com/apis/credentials", file=sys.stderr)
        print("  Create Credentials → OAuth client ID → Desktop app → Download JSON", file=sys.stderr)
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
        print(f"  Auth token saved to {token_path.name}")

    return build("sheets", "v4", credentials=creds)


def fetch_sheet(service, sheet_id: str, sheet_name: str) -> list:
    """
    Read columns A and B from a Google Sheet tab via the Sheets API.

    Returns a list of (front, back) string tuples, with blank rows and
    detected header rows excluded.
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{sheet_name}'!A:B",
        ).execute()
    except Exception as exc:
        print(f"  ERROR reading sheet '{sheet_name}': {exc}", file=sys.stderr)
        return []

    rows = result.get("values", [])

    # Common header labels — skip the first row if it looks like column names
    HEADER_LABELS = {
        "word", "phrase", "front", "back", "term", "translation",
        "vocab", "vocabulary", "native", "target", "english", "spanish",
        "french", "german", "italian", "portuguese", "japanese", "chinese",
        "korean", "arabic", "russian",
    }

    pairs = []
    for i, row in enumerate(rows):
        if len(row) < 2:
            continue
        front = str(row[0]).strip()
        back = str(row[1]).strip()
        if not front or not back:
            continue
        # Skip header row if the first cell is a known label
        if i == 0 and front.lower() in HEADER_LABELS:
            continue
        pairs.append((front, back))

    return pairs


# ---------------------------------------------------------------------------
# Anki helpers
# ---------------------------------------------------------------------------

def card_exists_in_anki(ankiweb_bin: str, front: str) -> bool:
    """
    Return True if a card with the given Front field already exists in Anki.
    Quotes the phrase so multi-word fronts work correctly.
    """
    # Escape any double quotes in the front value to avoid breaking the search syntax
    safe_front = front.replace('"', '\\"')
    query = f'Front:"{safe_front}"'
    code, stdout, _ = run_cmd([ankiweb_bin, "cards", "search", query, "--json"])
    if code != 0:
        # On search failure, assume not found and let add attempt proceed
        return False
    try:
        results = json.loads(stdout)
        return isinstance(results, list) and len(results) > 0
    except json.JSONDecodeError:
        return False


def add_note(
    ankiweb_bin: str,
    deck_id: str,
    notetype_id: str,
    front: str,
    back: str,
    dry_run: bool,
) -> bool:
    """
    Add a note to Anki with the given Front/Back fields.
    Returns True on success (or in dry-run mode).
    """
    cmd = [
        ankiweb_bin, "notes", "add",
        "--notetype-id", notetype_id,
        "--deck-id", deck_id,
        "--field", front,
        "--field", back,
    ]

    if dry_run:
        print(f"  [DRY RUN] ADD  {front} → {back}")
        return True

    code, stdout, stderr = run_cmd(cmd)
    if code != 0:
        print(f"  ERROR adding '{front}': {stderr or stdout}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Log file
# ---------------------------------------------------------------------------

def write_log(
    log_path: Path,
    language: str,
    target_sheet: str,
    native_sheet: str,
    target_count: int,
    native_count: int,
    unique_total: int,
    added: list,
    skipped: list,
    errors: list,
):
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Sync run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {language}\n")
        f.write(f"Target language sheet ('{target_sheet}'): {target_count} entries\n")
        f.write(f"Native language sheet ('{native_sheet}'): {native_count} entries\n")
        f.write(f"Total unique entries: {unique_total}\n")
        f.write(f"New notes added: {len(added)}  (→ {len(added) * 2} Anki cards)\n")
        f.write(f"Skipped (already exist): {len(skipped)}\n")
        f.write(f"Errors: {len(errors)}\n")
        f.write("---\n")
        for front, back, source in added:
            f.write(f"Added:   {front} → {back}  [from {source}]\n")
        for front, back, source in skipped:
            f.write(f"Skipped: {front}  (already in deck)\n")
        for front, back, source in errors:
            f.write(f"ERROR:   {front} → {back}  [from {source}]\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sync vocabulary from a Google Sheet to Anki flashcards.\n"
            "Creates bidirectional cards (2 per entry) using the\n"
            "'Basic (and reversed card)' notetype. Works for any language."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be added without creating any Anki cards.",
    )
    parser.add_argument(
        "--sheet-id",
        help="Google Sheet ID (overrides GOOGLE_SHEET_ID in .env).",
    )
    parser.add_argument(
        "--target-sheet",
        help="Tab name for the target-language sheet (overrides TARGET_LANG_SHEET in .env).",
    )
    parser.add_argument(
        "--native-sheet",
        help="Tab name for the native-language sheet (overrides NATIVE_LANG_SHEET in .env).",
    )
    args = parser.parse_args()

    # --- Load config ---
    sheet_id     = args.sheet_id     or get_env("GOOGLE_SHEET_ID")
    target_sheet = args.target_sheet or os.getenv("TARGET_LANG_SHEET", "Sheet1")
    native_sheet = args.native_sheet or os.getenv("NATIVE_LANG_SHEET", "Sheet2")
    language     = os.getenv("LEARNING_LANGUAGE", "target")
    deck_id      = get_env("ANKI_DECK_ID")
    notetype_id  = get_env("ANKI_NOTETYPE_ID")
    ankiweb_bin  = get_env("ANKIWEB_CLI_PATH")

    project_root = Path(__file__).parent.parent
    tmp_dir = project_root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = tmp_dir / f"vocab_sync_{timestamp}.txt"

    if args.dry_run:
        print("=" * 55)
        print("  DRY RUN — no Anki cards will be created")
        print("=" * 55)
        print()

    # --- Authenticate with Google Sheets API ---
    print("Connecting to Google Sheets...")
    service = get_sheets_service(project_root)
    print("  Connected.")

    # --- Fetch both sheets ---
    print(f"Reading '{target_sheet}' ({language} → native)...")
    target_pairs = fetch_sheet(service, sheet_id, target_sheet)
    print(f"  {len(target_pairs)} entries found.")

    print(f"Reading '{native_sheet}' (native → {language})...")
    native_pairs = fetch_sheet(service, sheet_id, native_sheet)
    print(f"  {len(native_pairs)} entries found.")

    # Tag each entry with its source sheet, then combine
    all_entries = (
        [(front, back, target_sheet) for front, back in target_pairs]
        + [(front, back, native_sheet) for front, back in native_pairs]
    )

    # Deduplicate within this run by Front value (case-insensitive)
    seen: set = set()
    unique_entries = []
    for front, back, source in all_entries:
        key = front.lower()
        if key not in seen:
            seen.add(key)
            unique_entries.append((front, back, source))

    total = len(unique_entries)
    print(f"\nTotal unique entries: {total}")
    print("Checking for existing Anki cards and syncing new ones...\n")

    # --- Process each entry ---
    added: list = []
    skipped: list = []
    errors: list = []

    for front, back, source in unique_entries:
        if card_exists_in_anki(ankiweb_bin, front):
            skipped.append((front, back, source))
            print(f"  SKIP  {front}")
        else:
            success = add_note(
                ankiweb_bin, deck_id, notetype_id, front, back, args.dry_run
            )
            if success:
                added.append((front, back, source))
                if not args.dry_run:
                    print(f"  ADD   {front} → {back}  [{source}]")
            else:
                errors.append((front, back, source))

    # --- Print summary ---
    verb = "Would add" if args.dry_run else "Added"
    print()
    print("=" * 55)
    print(
        f"{'DRY RUN ' if args.dry_run else ''}Sync complete — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"  Language:                {language}")
    print(f"  '{target_sheet}' (target): {len(target_pairs)} entries")
    print(f"  '{native_sheet}' (native): {len(native_pairs)} entries")
    print(f"  Total unique:            {total}")
    print(f"  {verb}:              {len(added)} notes  (→ {len(added) * 2} Anki cards)")
    print(f"  Skipped (already exist): {len(skipped)}")
    print(f"  Errors:                  {len(errors)}")

    if not args.dry_run:
        write_log(
            log_path,
            language,
            target_sheet,
            native_sheet,
            len(target_pairs),
            len(native_pairs),
            total,
            added,
            skipped,
            errors,
        )
        print(f"\nLog written to: {log_path.relative_to(project_root)}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
