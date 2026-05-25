# Workflow: Sync Vocabulary Sheet → Anki Flashcards

> Reads word/phrase pairs from a two-tab Google Sheet and creates bidirectional Anki flashcards for any language pair.

---

## Objective

A successful run reads new entries from both tabs of the vocabulary Google Sheet, skips anything already in the Anki deck, and adds the rest as "Basic (and reversed card)" notes — producing 2 Anki cards per entry (target→native and native→target). A log is written to `.tmp/` with a full record of what was added, skipped, and errored.

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| `GOOGLE_SHEET_ID` | `.env` | The ID in your Sheet URL: `…/spreadsheets/d/<ID>/edit` |
| `TARGET_LANG_SHEET` | `.env` | Tab name where col A = word in the language being learned |
| `NATIVE_LANG_SHEET` | `.env` | Tab name where col A = native-language word/phrase |
| `LEARNING_LANGUAGE` | `.env` | Display name for logs, e.g. `Spanish` (optional) |
| `ANKI_DECK_ID` | `.env` | Numeric Anki deck ID — get via `ankiweb decks list --json` |
| `ANKI_NOTETYPE_ID` | `.env` | Notetype ID for "Basic (and reversed card)" — get via `ankiweb notes editor-info --json` |
| `ANKIWEB_CLI_PATH` | `.env` | Full path to the `ankiweb-pp-cli-pp-cli` binary |

## Tools Used

| Tool | Purpose |
|------|---------|
| `tools/sync_vocab_to_anki.py` | Reads both sheet tabs, checks Anki for duplicates, adds new notes, writes log |
| `gog` (gogcli) | Reads Google Sheet values via `gog sheets get` |
| `ankiweb-pp-cli-pp-cli` | Searches existing cards (`cards search`) and adds new notes (`notes add`) |

## One-Time Setup

Before the first run, complete these steps once:

**1. Find your Anki notetype ID**
```powershell
& $env:ANKIWEB_CLI_PATH notes editor-info --json
```
Look for the entry named `"Basic (and reversed card)"` and copy its `id`.

**2. Find your Anki deck ID**
```powershell
& $env:ANKIWEB_CLI_PATH decks list --json
```
Copy the `id` of the deck you want cards added to.

**3. Get your Google Sheet ID**
From your sheet URL: `https://docs.google.com/spreadsheets/d/<THIS_PART>/edit`

**4. Populate `.env`**
Copy `.env.example` to `.env` and fill in all values under the vocab sync section.

**5. Verify Google auth**
```powershell
gog auth list --check
```
If not authenticated, run `gog auth add <your-email>`.

## Steps

1. **Dry run first** — preview without touching Anki:
   ```powershell
   python tools/sync_vocab_to_anki.py --dry-run
   ```
   Review the output — confirm the right entries would be added.

2. **Live run** — sync new entries to Anki:
   ```powershell
   python tools/sync_vocab_to_anki.py
   ```

3. **Check the log** — confirm counts and review any errors:
   ```powershell
   Get-Content (Get-ChildItem .tmp\vocab_sync_*.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
   ```

4. **Verify in Anki** — card count should have increased by 2× the number of new entries:
   ```powershell
   & $env:ANKIWEB_CLI_PATH decks list
   ```

## Scheduling

To run automatically (e.g. daily), use `/schedule` in Claude Code:
```
python C:\Users\paulb\Documents\Agentic Workflows\CatchAndRelease\tools\sync_vocab_to_anki.py
```

## Edge Cases & Known Quirks

- **Header row detection** — if the first row of a tab has a cell matching a common label (`word`, `phrase`, `front`, `translation`, etc.) it is automatically skipped. If your headers aren't detected, just leave the first data row as-is; it will be treated as a vocab entry.
- **Multi-word phrases** — handled correctly. The duplicate check wraps the phrase in quotes: `Front:"Buenos días"`.
- **Duplicate detection** — searches by `Front` field only. If the same phrase appears on both sheet tabs (with the same or different translations), only the first occurrence is processed.
- **Google auth expiry** — `gog` OAuth tokens refresh automatically. If you see a 401 error, run `gog auth list --check` to re-authenticate.
- **AnkiWeb auth expiry** — session cookies expire. Re-authenticate with:
  `& $env:ANKIWEB_CLI_PATH account login --username <email>`
- **Rate limits** — the AnkiWeb CLI defaults to 2 req/s. For large sheets (100+ entries), the run may take a minute or two — this is expected.
- **Field name mismatch** — if your notetype uses different field names than `Front`/`Back`, the `notes add` calls will fail. Verify field names with:
  `& $env:ANKIWEB_CLI_PATH notes fields --notetype-id <ID>`
  Then update the `--field` arguments in `tools/sync_vocab_to_anki.py`.

## Output

- **Intermediate:** `.tmp/vocab_sync_YYYYMMDD_HHMMSS.txt` — full log of added/skipped/errored entries
- **Final:** Anki deck (cloud) — new flashcards available immediately for study

---

*Last updated: 2026-05-25 — initial version, language-agnostic design*
