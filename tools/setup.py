#!/usr/bin/env python3
"""
setup.py — CatchAndRelease onboarding wizard

Walks a new user through every setup step needed to run sheets_to_anki.py:
  1. Python dependencies
  2. Google Cloud credentials (credentials.json)
  3. Google OAuth authorization (token.json)
  4. Google Sheet creation
  5. AnkiWeb account
  6. AnkiWeb session cookie
  7. AnkiWeb deck selection
  8. Note type verification
  9. Write .env
 10. Final dry run (optional)

Run this once before using the workflow. Safe to re-run — completed steps are
detected and skipped automatically.
"""

import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

# Ensure Unicode characters print correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE     = PROJECT_ROOT / ".env"
SCOPES       = ["https://www.googleapis.com/auth/spreadsheets"]

DEFAULT_ANKIWEB_CLI = str(
    Path.home() / "printing-press" / "library" / "ankiweb" / "ankiweb-pp-cli.exe"
)

# Full list of Google-supported language codes (used for GOOGLETRANSLATE formula)
# Source: https://developers.google.com/workspace/admin/directory/v1/languages
SUPPORTED_LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "as": "Assamese", "az": "Azerbaijani", "eu": "Basque",
    "bn": "Bengali", "bg": "Bulgarian", "my": "Burmese", "ca": "Catalan",
    "chr": "Cherokee", "zh-HK": "Chinese (Hong Kong)", "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)", "hr": "Croatian", "cs": "Czech",
    "da": "Danish", "nl": "Dutch", "en-GB": "English (UK)", "en": "English (US)",
    "et": "Estonian", "fil": "Filipino", "fi": "Finnish", "fr": "French",
    "fr-CA": "French (Canada)", "gl": "Galician", "ka": "Georgian", "de": "German",
    "el": "Greek", "gu": "Gujarati", "iw": "Hebrew", "hi": "Hindi",
    "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian", "ga": "Irish",
    "it": "Italian", "ja": "Japanese", "kn": "Kannada", "kk": "Kazakh",
    "km": "Khmer", "ko": "Korean", "lo": "Lao", "lv": "Latvian",
    "lt": "Lithuanian", "mk": "Macedonian", "ms": "Malay", "ml": "Malayalam",
    "mr": "Marathi", "mn": "Mongolian", "ne": "Nepali", "no": "Norwegian",
    "or": "Oriya", "fa": "Persian", "pl": "Polish", "pt-BR": "Portuguese (Brazil)",
    "pt-PT": "Portuguese (Portugal)", "pa": "Punjabi", "ro": "Romanian",
    "ru": "Russian", "sr": "Serbian", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "es": "Spanish", "es-419": "Spanish (Latin America)",
    "sw": "Swahili", "sv": "Swedish", "ta": "Tamil", "te": "Telugu",
    "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh", "zu": "Zulu",
}

# Languages shown first in the picker (most common for language learners)
COMMON_LANG_CODES = [
    "es", "fr", "de", "it", "pt-BR", "ja", "ko", "zh-CN",
    "ru", "ar", "hi", "tr", "nl", "sv", "pl", "vi",
]


def select_language(prompt_text: str, default_code: str = None) -> tuple:
    """
    Interactive language picker. Shows common languages by number, also
    accepts a language code (e.g. "es") or partial name search (e.g. "span").
    Returns (code, name).
    """
    common = [(c, SUPPORTED_LANGUAGES[c]) for c in COMMON_LANG_CODES if c in SUPPORTED_LANGUAGES]

    print(f"\n  {prompt_text}\n")
    for i, (code, name) in enumerate(common, 1):
        print(f"    {i:2}. {name:<30} ({code})")

    default_label = None
    if default_code and default_code in SUPPORTED_LANGUAGES:
        default_label = f"{SUPPORTED_LANGUAGES[default_code]} ({default_code})"

    print(f"\n  Enter a number, a code (e.g. 'es'), or part of a name (e.g. 'span' → Spanish)")

    while True:
        val = prompt("Your choice", default=default_label).strip()

        # Number from the common list
        try:
            idx = int(val) - 1
            if 0 <= idx < len(common):
                code, name = common[idx]
                ok(f"Selected: {name} ({code})")
                return code, name
            else:
                print(f"  Please enter a number between 1 and {len(common)}")
                continue
        except ValueError:
            pass

        # Exact code match (case-insensitive)
        lower = val.lower()
        exact = [(c, n) for c, n in SUPPORTED_LANGUAGES.items() if c.lower() == lower]
        if exact:
            code, name = exact[0]
            ok(f"Selected: {name} ({code})")
            return code, name

        # Partial name search
        matches = [(c, n) for c, n in SUPPORTED_LANGUAGES.items() if lower in n.lower()]
        if len(matches) == 1:
            code, name = matches[0]
            ok(f"Selected: {name} ({code})")
            return code, name
        elif len(matches) > 1:
            print(f"\n  Multiple matches for '{val}':")
            for c, n in matches[:8]:
                print(f"    {n} ({c})")
            if len(matches) > 8:
                print(f"    … and {len(matches) - 8} more. Try a more specific term.")
            continue

        print(f"  Not found: '{val}'. Try a number, a code like 'es', or a name like 'Spanish'.")


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

def header(n: int, title: str):
    print(f"\n{'─' * 60}")
    print(f"  STEP {n} of 10: {title}")
    print(f"{'─' * 60}")


def ok(msg: str):
    print(f"  ✓  {msg}")


def info(msg: str):
    print(f"  •  {msg}")


def warn(msg: str):
    print(f"  ⚠  {msg}", file=sys.stderr)


def err(msg: str):
    print(f"  ✗  {msg}", file=sys.stderr)


def skipped(msg: str):
    print(f"  ↩  Already done: {msg}")


def prompt(msg: str, default: str = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default and not secret else ""
    while True:
        val = input(f"\n  → {msg}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        print("  (required — please enter a value)")


def yesno(msg: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"\n  → {msg}{suffix}: ").strip().lower()
    if not val:
        return default
    return val.startswith("y")


def open_browser(url: str, label: str = ""):
    label = label or url
    info(f"Opening browser: {label}")
    webbrowser.open(url)


def mask(value: str, keep: int = 12) -> str:
    """Show only the first few characters of a sensitive value."""
    if len(value) <= keep:
        return value
    return value[:keep] + "…"


def run_cmd(cmd: list, extra_env: dict = None) -> tuple:
    """Run a subprocess. Returns (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", env=env
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", f"Command not found: {cmd[0]} — {exc}"


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------

def read_env() -> dict:
    """Read the .env file and return a dict of key → value (values unquoted)."""
    if not ENV_FILE.exists():
        return {}
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip().strip('"').strip("'")
            values[key] = val
    return values


def write_env_keys(updates: dict):
    """
    Update or append keys in the .env file.
    Preserves existing comments, blank lines, and unrelated keys.
    """
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    written = set()

    # Update existing lines in-place
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    # Append any keys not already present
    remaining = {k: v for k, v in updates.items() if k not in written}
    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")  # blank line before new section
        for key, val in remaining.items():
            new_lines.append(f"{key}={val}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1: Python dependencies
# ---------------------------------------------------------------------------

def step1_dependencies():
    header(1, "Python dependencies")
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        warn("requirements.txt not found — skipping dependency install")
        return

    info("Running: pip install -r requirements.txt")
    code, stdout, stderr = run_cmd([sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"])
    if code != 0:
        err(f"pip install failed:\n{stderr or stdout}")
        print("\n  Please fix the above error and re-run setup.py.")
        sys.exit(1)

    # Verify key imports
    missing = []
    for pkg in ["dotenv", "google.auth", "googleapiclient", "openpyxl"]:
        try:
            __import__(pkg.replace(".", "_") if pkg == "dotenv" else pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        err(f"Some packages still missing after install: {', '.join(missing)}")
        sys.exit(1)

    ok("All dependencies installed")


# ---------------------------------------------------------------------------
# Step 2: Google Cloud credentials
# ---------------------------------------------------------------------------

def step2_credentials() -> Path:
    header(2, "Google Cloud credentials (credentials.json)")

    env = read_env()
    creds_name = env.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    creds_path = Path(creds_name) if Path(creds_name).is_absolute() else PROJECT_ROOT / creds_name

    if creds_path.exists():
        # Validate it's a real OAuth credentials file
        try:
            data = json.loads(creds_path.read_text(encoding="utf-8"))
            if "installed" in data or "web" in data:
                skipped(f"credentials.json found at {creds_path.name}")
                return creds_path
            else:
                warn("credentials.json exists but doesn't look like an OAuth file — re-downloading")
        except (json.JSONDecodeError, OSError):
            warn("credentials.json exists but is unreadable — re-downloading")

    print("""
  You need to download OAuth credentials from Google Cloud Console.
  Here's what to do (takes about 3 minutes):

    1. A browser tab will open to Google Cloud Console
    2. If prompted, create a new project (call it anything, e.g. "AnkiSync")
    3. Click "ENABLE APIS AND SERVICES" → search "Google Sheets API" → Enable it
    4. Go back to Credentials → click "+ CREATE CREDENTIALS" → "OAuth client ID"
    5. Application type: Desktop app  →  Name: anything  →  click Create
    6. Click "DOWNLOAD JSON" on the popup
    7. Rename the downloaded file to  credentials.json
    8. Move it into this folder:  """ + str(PROJECT_ROOT) + """
""")

    open_browser(
        "https://console.cloud.google.com/apis/credentials",
        "Google Cloud Console → Credentials"
    )

    while True:
        input("  → Press Enter once you've saved credentials.json in the project folder...")
        if creds_path.exists():
            try:
                data = json.loads(creds_path.read_text(encoding="utf-8"))
                if "installed" in data or "web" in data:
                    ok("credentials.json found and valid")
                    return creds_path
                else:
                    err("That file doesn't look like Google OAuth credentials. Please re-download.")
            except (json.JSONDecodeError, OSError):
                err("Could not read the file. Please make sure you saved it correctly.")
        else:
            err(f"File not found at: {creds_path}")
            info(f"Make sure it's named exactly 'credentials.json' and is in: {PROJECT_ROOT}")


# ---------------------------------------------------------------------------
# Step 3: Google authorization
# ---------------------------------------------------------------------------

def step3_google_auth(creds_path: Path):
    header(3, "Google authorization")

    # Lazy import — only available after step 1
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    env = read_env()
    token_name = env.get("GOOGLE_TOKEN_FILE", "token.json")
    token_path = Path(token_name) if Path(token_name).is_absolute() else PROJECT_ROOT / token_name

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        # Verify it has read+write scope
        if "spreadsheets" in " ".join(creds.scopes or []):
            skipped("Google already authorized with read+write access")
            return build("sheets", "v4", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        info("Refreshing expired Google token...")
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            ok("Token refreshed")
            return build("sheets", "v4", credentials=creds)
        except Exception as exc:
            warn(f"Token refresh failed ({exc}) — re-authorizing")

    print("""
  A browser tab will open asking you to sign in with your Google account
  and grant permission to read and write Google Sheets.

  This is a one-time step — your permission is saved for future runs.
""")

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    ok("Google authorization complete — token saved")

    return build("sheets", "v4", credentials=creds)


# ---------------------------------------------------------------------------
# Step 4: Create Google Sheet
# ---------------------------------------------------------------------------

def step4_create_sheet(service) -> tuple:
    """Returns (sheet_id, target_lang_code, native_lang_code)."""
    header(4, "Google Sheet setup + language selection")

    env = read_env()
    existing_id     = env.get("GOOGLE_SHEET_ID", "").strip()
    existing_target = env.get("ANKI_TARGET_LANG", "").strip()
    existing_native = env.get("ANKI_NATIVE_LANG", "en").strip()

    if existing_id:
        try:
            service.spreadsheets().get(spreadsheetId=existing_id).execute()
            skipped(f"Sheet already configured (ID: {existing_id[:20]}…)")
            return existing_id, existing_target or "es", existing_native or "en"
        except Exception:
            warn("GOOGLE_SHEET_ID is set but the sheet isn't accessible — creating a new one")

    # Language selection
    print("\n  First, tell us about the language you're learning.")
    print("  This sets up auto-translation in your sheet using Google Translate.")

    target_code, target_name = select_language(
        "What language are you learning?",
        default_code=existing_target or None,
    )
    native_code, native_name = select_language(
        "What is your native language? (translations will appear in this language)",
        default_code=existing_native or "en",
    )

    sheet_title = prompt(
        "What would you like to name your vocabulary sheet?",
        default=f"{target_name} Vocabulary",
    )
    tab_name = prompt("Tab name for your vocabulary list?", default="Translate")

    info(f"Creating Google Sheet: \"{sheet_title}\"...")

    spreadsheet = service.spreadsheets().create(body={
        "properties": {"title": sheet_title},
        "sheets": [{"properties": {"title": tab_name}}],
    }).execute()

    sheet_id = spreadsheet["spreadsheetId"]
    gid      = spreadsheet["sheets"][0]["properties"]["sheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    # Header row uses language names as column labels
    header_row = [target_name, native_name, "", "Done"]

    # Sample rows with GOOGLETRANSLATE formula pre-filled in column B.
    # Formula: =GOOGLETRANSLATE(A2, "es", "en") — auto-translates whatever is in column A.
    # Pre-populate rows 2–51 so users can just type in column A without touching formulas.
    data_rows = []
    for row_num in range(2, 52):
        formula = f'=IF(A{row_num}<>"",GOOGLETRANSLATE(A{row_num},"{target_code}","{native_code}"),"")'
        data_rows.append(["", formula, "", ""])

    # Overwrite first two data rows with example entries
    example_word = {"es": "hola", "fr": "bonjour", "de": "hallo", "it": "ciao",
                    "ja": "こんにちは", "ko": "안녕하세요", "pt-BR": "olá"}.get(target_code, "hello")
    data_rows[0][0] = example_word
    data_rows[1][0] = ""  # leave row 3 blank as a visual separator

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1:D{1 + len(data_rows)}",
        valueInputOption="USER_ENTERED",
        body={"values": [header_row] + data_rows},
    ).execute()

    # Formatting: bold header, freeze row 1, column widths
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [
            # Bold header row
            {"repeatCell": {
                "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }},
            # Freeze row 1
            {"updateSheetProperties": {
                "properties": {
                    "sheetId": gid,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }},
            # Column A width: 250
            {"updateDimensionProperties": {
                "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 250},
                "fields": "pixelSize",
            }},
            # Column B width: 250
            {"updateDimensionProperties": {
                "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 250},
                "fields": "pixelSize",
            }},
            # Column D width: 80
            {"updateDimensionProperties": {
                "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
                "properties": {"pixelSize": 80},
                "fields": "pixelSize",
            }},
        ]},
    ).execute()

    ok(f"Sheet created: {sheet_title}")
    ok(f"Column A: {target_name}  →  Column B: auto-translated to {native_name} via GOOGLETRANSLATE")
    ok(f"Rows 2–51 pre-loaded with translation formulas — just type in column A")
    ok(f"URL: {sheet_url}")
    open_browser(sheet_url, sheet_title)

    write_env_keys({"GOOGLE_SHEET_TAB": tab_name})

    return sheet_id, target_code, native_code


# ---------------------------------------------------------------------------
# Step 5: AnkiWeb account
# ---------------------------------------------------------------------------

def step5_ankiweb_account():
    header(5, "AnkiWeb account")

    has_account = yesno("Do you already have an AnkiWeb account?", default=True)

    if not has_account:
        print("""
  You'll need a free AnkiWeb account to sync your flashcards.
  A browser tab will open to the sign-up page.
""")
        open_browser("https://ankiweb.net/account/register", "AnkiWeb sign up")
        input("  → Press Enter once you've created and verified your account...")
    else:
        info("Opening ankiweb.net — make sure you're logged in")
        open_browser("https://ankiweb.net", "AnkiWeb")
        input("  → Press Enter once you're logged in to ankiweb.net...")

    ok("AnkiWeb account ready")


# ---------------------------------------------------------------------------
# Step 6: AnkiWeb session cookie
# ---------------------------------------------------------------------------

def step6_ankiweb_cookie(ankiweb_bin: str) -> str:
    header(6, "AnkiWeb session cookie")

    env = read_env()
    existing_cookie = env.get("ANKIWEB_COOKIES", "").strip()

    if existing_cookie:
        info("Checking existing cookie...")
        code, _, _ = run_cmd(
            [ankiweb_bin, "doctor", "--no-color"],
            extra_env={"ANKIWEB_COOKIES": existing_cookie},
        )
        if code == 0:
            skipped(f"Cookie valid ({mask(existing_cookie)})")
            return existing_cookie
        else:
            warn("Existing cookie has expired — need a fresh one")

    print("""
  To connect to AnkiWeb, we need to copy your session cookie from Chrome.
  Here's how (takes about 30 seconds):

  ┌──────────────────────────────────────────────────────┐
  │  1. In Chrome, go to ankiweb.net (you just logged in) │
  │  2. Press  F12  to open Developer Tools               │
  │  3. Click the  Application  tab                       │
  │  4. In the left sidebar: Cookies → https://ankiweb.net│
  │  5. Find the row where Name = "ankiweb"               │
  │  6. Click on that row and copy the entire Value       │
  └──────────────────────────────────────────────────────┘
""")

    for attempt in range(1, 4):
        raw = prompt("Paste the cookie value here")
        # Accept both "ankiweb=<value>" and bare "<value>"
        if not raw.startswith("ankiweb="):
            raw = f"ankiweb={raw}"

        info("Validating cookie with AnkiWeb CLI...")
        code, stdout, stderr = run_cmd(
            [ankiweb_bin, "doctor", "--no-color"],
            extra_env={"ANKIWEB_COOKIES": raw},
        )

        if code == 0:
            ok(f"Cookie valid ({mask(raw)})")
            return raw
        else:
            output = stderr or stdout
            err(f"Cookie validation failed: {output}")
            if attempt < 3:
                warn(f"Attempt {attempt}/3 — please try again")
            else:
                err("Could not validate cookie after 3 attempts.")
                print("\n  Make sure you:\n  • Are still logged in to ankiweb.net\n  • Copied the full Value (it's a long string)\n  • Didn't accidentally copy a different cookie row")
                sys.exit(1)

    return ""  # unreachable


# ---------------------------------------------------------------------------
# Step 7: AnkiWeb deck selection
# ---------------------------------------------------------------------------

def step7_ankiweb_deck(ankiweb_bin: str, cookie: str) -> str:
    header(7, "AnkiWeb deck")

    env = read_env()
    existing_deck = env.get("ANKI_DECK", "").strip()
    if existing_deck:
        skipped(f"Deck already configured: \"{existing_deck}\"")
        return existing_deck

    for attempt in range(1, 4):
        code, stdout, stderr = run_cmd(
            [ankiweb_bin, "decks", "list", "--json", "--no-color", "--no-input"],
            extra_env={"ANKIWEB_COOKIES": cookie},
        )

        if code != 0:
            err(f"Could not fetch deck list: {stderr or stdout}")
            if attempt < 3:
                input("  → Press Enter to retry...")
            else:
                sys.exit(1)
            continue

        try:
            decks = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            decks = []

        # Clean up deck names — strip leading non-printable characters from protobuf encoding
        def clean_name(raw: str) -> str:
            # Keep only printable characters; collapse leading junk
            cleaned = re.sub(r'^[^\x20-\x7EÀ-ɏ]+', '', raw).strip()
            # If still empty after strip, fall back to repr
            return cleaned if cleaned else raw

        named = [(clean_name(d.get("name", "")), d) for d in decks if isinstance(d, dict)]
        named = [(n, d) for n, d in named if n]  # drop empty names

        if not named:
            warn("No decks found in your AnkiWeb account.")
            print("""
  You need at least one deck in AnkiWeb before we can continue.

  How to create a deck:
    1. Open ankiweb.net in your browser
    2. Click "Add Deck" or use the Anki desktop app to create one and sync it
""")
            open_browser("https://ankiweb.net", "AnkiWeb — create a deck")
            input("  → Press Enter once you've created a deck and it's synced to AnkiWeb...")
            continue

        print(f"\n  Found {len(named)} deck(s):\n")
        for i, (name, _) in enumerate(named, 1):
            print(f"    {i}. {name}")

        while True:
            choice = prompt(f"Enter the number of the deck to use (1–{len(named)})")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(named):
                    deck_name = named[idx][0]
                    ok(f"Selected deck: \"{deck_name}\"")
                    return deck_name
                else:
                    print(f"  Please enter a number between 1 and {len(named)}")
            except ValueError:
                print("  Please enter a number")

    return ""  # unreachable


# ---------------------------------------------------------------------------
# Step 8: Verify note type
# ---------------------------------------------------------------------------

def step8_verify_notetype(ankiweb_bin: str, cookie: str):
    header(8, "Note type check")

    TARGET = "Basic (and reversed card)"

    code, stdout, stderr = run_cmd(
        [ankiweb_bin, "notetypes", "--json", "--no-color", "--no-input"],
        extra_env={"ANKIWEB_COOKIES": cookie},
    )

    if code != 0:
        warn(f"Could not fetch note types ({stderr or stdout}) — skipping check")
        info(f"Assuming \"{TARGET}\" exists (default Anki note type)")
        return

    try:
        data = json.loads(stdout)
        # notetypes returns an object; look for note_types array or similar
        note_types = []
        if isinstance(data, list):
            note_types = data
        elif isinstance(data, dict):
            note_types = data.get("note_types") or data.get("noteTypes") or []

        names = [nt.get("name", "") for nt in note_types if isinstance(nt, dict)]

        if any(TARGET.lower() in n.lower() for n in names):
            ok(f"Note type found: \"{TARGET}\"")
        else:
            warn(f"\"{TARGET}\" not found in your note types.")
            if names:
                info("Available note types: " + ", ".join(f'"{n}"' for n in names[:5]))
            warn("Cards will be added using the default note type. Update ANKI_NOTETYPE in .env if needed.")
    except (json.JSONDecodeError, ValueError):
        warn("Could not parse note type response — skipping check")


# ---------------------------------------------------------------------------
# Step 9: Write .env
# ---------------------------------------------------------------------------

def step9_write_env(sheet_id: str, deck: str, cookie: str, ankiweb_bin: str,
                    target_lang: str, native_lang: str):
    header(9, "Saving configuration to .env")

    env = read_env()

    updates = {
        "ANKIWEB_COOKIES":  cookie,
        "GOOGLE_SHEET_ID":  sheet_id,
        "ANKI_DECK":        deck,
        "ANKIWEB_CLI_PATH": ankiweb_bin,
        "ANKI_TARGET_LANG": target_lang,
        "ANKI_NATIVE_LANG": native_lang,
    }

    # Set sensible defaults for anything not already configured
    defaults = {
        "GOOGLE_SHEET_TAB":   "Translate",
        "ANKI_HEADER_ROW":    "1",
        "ANKI_FRONT_COL":     "A",
        "ANKI_BACK_COL":      "B",
        "ANKI_DONE_COL":      "D",
        "ANKI_DONE_MARKER":   "✓",
        "ANKI_NOTETYPE":      "Basic (and reversed card)",
        "ANKI_TAGS":          "",
        "LOG_DIR":            ".tmp",
        "GOOGLE_CREDENTIALS_FILE": "credentials.json",
        "GOOGLE_TOKEN_FILE":  "token.json",
    }
    for key, val in defaults.items():
        if key not in env:
            updates[key] = val

    write_env_keys(updates)

    print("\n  Your .env is now configured:")
    masked_updates = {
        k: (mask(v) if "COOKIE" in k else v)
        for k, v in updates.items()
        if v  # skip empty values
    }
    for k, v in masked_updates.items():
        print(f"    {k}={v}")

    ok(".env saved")


# ---------------------------------------------------------------------------
# Step 10: Final dry run
# ---------------------------------------------------------------------------

def step10_dry_run():
    header(10, "Final check")

    if not yesno("Run a quick dry run to confirm everything works?", default=True):
        info("Skipping dry run — you can run it later with:  python tools/sheets_to_anki.py --dry-run")
        return

    info("Running: python tools/sheets_to_anki.py --dry-run")
    code, stdout, stderr = run_cmd([sys.executable, str(PROJECT_ROOT / "tools" / "sheets_to_anki.py"), "--dry-run"])

    output = stdout or stderr
    # Print the summary lines
    for line in output.splitlines():
        if any(kw in line for kw in ["Would add", "Skipped", "Errors", "Complete", "total rows", "DRY RUN"]):
            print(f"    {line.strip()}")

    if code == 0:
        ok("Dry run passed — you're all set!")
        print("""
  ┌──────────────────────────────────────────────────────┐
  │  You're ready to go!                                  │
  │                                                       │
  │  Add vocabulary rows to your Google Sheet, then run:  │
  │    python tools/sheets_to_anki.py --dry-run  (preview)│
  │    python tools/sheets_to_anki.py            (run)    │
  └──────────────────────────────────────────────────────┘
""")
    else:
        warn("Dry run encountered issues. Check the output above.")
        info("You can re-run setup.py at any time to fix any step.")


# ---------------------------------------------------------------------------
# AnkiWeb CLI detection
# ---------------------------------------------------------------------------

def find_ankiweb_cli() -> str:
    """Find the ankiweb-pp-cli binary — check default path, then PATH."""
    env = read_env()
    configured = env.get("ANKIWEB_CLI_PATH", "").strip()

    if configured and Path(configured).exists():
        return configured

    if Path(DEFAULT_ANKIWEB_CLI).exists():
        return DEFAULT_ANKIWEB_CLI

    # Try PATH
    code, stdout, _ = run_cmd(["where", "ankiweb-pp-cli"])
    if code == 0 and stdout:
        return stdout.splitlines()[0].strip()

    return ""


def prompt_for_cli() -> str:
    """Ask the user where the ankiweb-pp-cli binary is."""
    print(f"""
  The AnkiWeb CLI binary was not found at the default location:
    {DEFAULT_ANKIWEB_CLI}

  If you have it installed elsewhere, enter the full path now.
  If you don't have it yet, download it from:
    https://github.com/paulbockewitz/printing-press-library
""")
    open_browser("https://github.com/paulbockewitz/printing-press-library", "Printing Press Library")

    while True:
        path = prompt("Full path to ankiweb-pp-cli.exe")
        if Path(path).exists():
            ok(f"Found CLI at: {path}")
            return path
        else:
            err(f"File not found: {path}")
            if not yesno("Try a different path?", default=True):
                err("Cannot continue without the AnkiWeb CLI. Exiting.")
                sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║         CatchAndRelease — Setup Wizard                   ║
╚══════════════════════════════════════════════════════════╝

  This wizard will set up everything you need to automatically
  create Anki flashcards from a Google Sheet.

  It will walk you through 10 steps. Already-completed steps
  are detected and skipped automatically.

  Estimated time (first run): 5–10 minutes
""")

    if not yesno("Ready to begin?", default=True):
        print("  Run this script again when you're ready.")
        sys.exit(0)

    # Step 1: Dependencies
    step1_dependencies()

    # Now safe to lazy-import google libs (installed in step 1)

    # Locate AnkiWeb CLI early — needed for steps 6–8
    ankiweb_bin = find_ankiweb_cli()
    if not ankiweb_bin:
        ankiweb_bin = prompt_for_cli()
    else:
        ok(f"AnkiWeb CLI found at: {ankiweb_bin}")

    # Step 2: Google credentials
    creds_path = step2_credentials()

    # Step 3: Google auth
    service = step3_google_auth(creds_path)

    # Step 4: Google Sheet + language selection
    sheet_id, target_lang, native_lang = step4_create_sheet(service)

    # Step 5: AnkiWeb account
    step5_ankiweb_account()

    # Step 6: Cookie
    cookie = step6_ankiweb_cookie(ankiweb_bin)

    # Step 7: Deck
    deck = step7_ankiweb_deck(ankiweb_bin, cookie)

    # Step 8: Note type check
    step8_verify_notetype(ankiweb_bin, cookie)

    # Step 9: Write .env
    step9_write_env(sheet_id, deck, cookie, ankiweb_bin, target_lang, native_lang)

    # Step 10: Dry run
    step10_dry_run()


if __name__ == "__main__":
    main()
