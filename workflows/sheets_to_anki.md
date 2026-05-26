# Workflow: Google Sheet → Anki Cards

## Objective
Read rows from a Google Sheet and create `Basic (and reversed card)` Anki flashcards via the AnkiWeb CLI. After each card is created, write a checkmark (`✓`) to column D on that row. Re-runs skip already-checked rows (idempotent).

---

## Inputs

| Input | Where |
|---|---|
| Google Sheet (with front/back/done columns) | Configured in `.env` |
| AnkiWeb session cookie | `ANKIWEB_COOKIES` in `.env` |
| Google OAuth credentials | `credentials.json` in project root |

---

## One-Time Setup

### 1. Google Sheets credentials
Download `credentials.json` from [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
1. Create a project (or select existing)
2. Enable the **Google Sheets API** (`APIs & Services → Enable APIs`)
3. Create Credentials → OAuth 2.0 Client ID → Desktop application
4. Download JSON → save as `credentials.json` in the project root

`token.json` is created automatically on first run (browser OAuth flow). It refreshes automatically.

**Important:** This workflow uses **read+write** Google Sheets scope (to write checkmarks).
If you have an existing `token.json` from a readonly scope, delete it before running.

### 2. Find your Anki deck name
```powershell
$env:ANKIWEB_COOKIES="ankiweb=<your-cookie>"
ankiweb-pp-cli decks list --json
```
Copy the `name` value of your target deck into `ANKI_DECK` in `.env`.

### 3. Confirm the note type name
```powershell
ankiweb-pp-cli notetypes --json
```
The default `ANKI_NOTETYPE` is `Basic (and reversed card)` — confirm this matches what you see.

### 4. Fill in `.env`
```
GOOGLE_SHEET_ID=<spreadsheet-id-from-url>
GOOGLE_SHEET_TAB=Sheet1
ANKI_HEADER_ROW=1
ANKI_FRONT_COL=A
ANKI_BACK_COL=B
ANKI_DONE_COL=D
ANKI_DONE_MARKER=✓
ANKI_DECK=<your-deck-name>
ANKI_NOTETYPE=Basic (and reversed card)
ANKI_TAGS=
ANKIWEB_CLI_PATH=C:\Users\paulb\printing-press\library\ankiweb\ankiweb-pp-cli.exe
LOG_DIR=.tmp
```

---

## Running the Workflow

### Dry run (always start here)
```powershell
python tools/sheets_to_anki.py --dry-run
```
Shows which rows would be processed. No cards created, no checkmarks written.

### Live run
```powershell
python tools/sheets_to_anki.py
```
Processes uncheck rows, creates cards, writes `✓` to column D.

### Override sheet or deck at runtime
```powershell
python tools/sheets_to_anki.py --sheet-id <other-id> --deck "Other Deck"
```

---

## How It Works

1. Reads all rows from the configured sheet tab
2. Skips row 1 (header) if `ANKI_HEADER_ROW=1`
3. For each data row:
   - Skips if front or back cell is blank
   - Skips if column D already has any value (already processed)
   - Calls `ankiweb-pp-cli notes add <front> <back> --type "Basic (and reversed card)" --deck <deck> --yes --no-input`
   - On success: writes `✓` to column D of that row
   - On failure: logs error, continues to next row
4. Prints summary; writes timestamped log to `.tmp/`

Each row creates **2 Anki cards** (forward + reverse) because of the `Basic (and reversed card)` note type.

---

## Re-Run Safety

The script is **idempotent** — safe to re-run at any time:
- Rows with a checkmark in column D are skipped
- Only new/unchecked rows are processed
- No duplicate cards

---

## Refreshing the AnkiWeb Cookie

AnkiWeb session cookies expire. When the CLI returns an auth error:

1. Open Chrome and go to [ankiweb.net](https://ankiweb.net) — make sure you're logged in
2. Press `F12` → Application → Cookies → `https://ankiweb.net`
3. Copy the value of the `ankiweb` cookie
4. Update `.env`:
   ```
   ANKIWEB_COOKIES=ankiweb=<new-value>
   ```

---

## Logs

Each run writes a log to `.tmp/sheets_to_anki_YYYYMMDD_HHMMSS.txt`:

```
Run: 2026-05-26 14:32:01
Sheet: <sheet-id> / Sheet1
------------------------------------------------------------
ADDED:   Bonjour → Hello  [row 2]
ADDED:   Merci → Thank you  [row 3]
SKIPPED: Au revoir  [row 4] (already done)
ERROR:   Salut → Hi  [row 5] — HTTP 401
------------------------------------------------------------
Summary: 2 added, 1 skipped, 1 error(s)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `GOOGLE_SHEET_ID is not set` | Add it to `.env` |
| `credentials.json not found` | Download from Google Cloud Console (see Setup step 1) |
| Google OAuth browser doesn't open | Run from a terminal with a desktop session; or copy the URL printed to the terminal |
| `token.json` scope error | Delete `token.json` and re-run to re-authorize with read+write scope |
| AnkiWeb auth error (401/403) | Refresh `ANKIWEB_COOKIES` in `.env` (see Cookie section above) |
| Card created but checkmark missing | Run again — the script will try to add the card again; AnkiWeb CLI will handle the duplicate gracefully, then the checkmark will be written |
| Wrong deck | Run `ankiweb-pp-cli decks list` to confirm the deck name, update `ANKI_DECK` in `.env` |
