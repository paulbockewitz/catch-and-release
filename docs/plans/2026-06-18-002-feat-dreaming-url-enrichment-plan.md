---
title: "feat: Add Dreaming.com URL enrichment to vocabulary sync"
date: 2026-06-18
origin: docs/brainstorms/2026-06-18-dreaming-url-enrichment-requirements.md
depth: lightweight
---

# feat: Add Dreaming.com URL Enrichment to Vocabulary Sync

## Summary

A new standalone tool `tools/enrich_dreaming_urls.py` enriches the vocabulary Google Sheet with Dreaming.com video URLs by querying the dreaming-pp-cli `concordance` command for each Spanish word. The tool runs after the existing Anki sync and writes the first concordance hit URL + match count (or `no matches`) to a dedicated sheet column, appending a timestamped run summary to a log file for auditability of scheduled/invisible runs.

---

## Problem Frame

The vocabulary sync (`sheets_to_anki.py`) creates Anki cards but provides no link to native-speaker video context. The dreaming-pp-cli already has a `concordance` command that searches transcripts and returns `https://app.dreaming.com/spanish/watch?id=<id>` URLs, but these systems are unconnected. Wiring them together lets the vocabulary sheet serve as a study hub where each word links directly to a Dreaming.com video.

---

## Requirements

- **R1** — For each row with a Spanish word and an empty URL column, query `dreaming-pp-cli concordance <word> --json --limit 50` and write the first hit URL + match count.
- **R2** — Rows already having any value in the URL column are skipped (idempotent).
- **R3** — Words with zero concordance hits receive `no matches`. No fuzzy fallback; `no matches` rows stay that way on re-runs.
- **R4** — Run summary appended to log file; per-row errors logged before the summary line.
- **R5** — Tool exits cleanly when `dreaming-pp-cli` is not on PATH, with a human-readable warning.

*(see origin: docs/brainstorms/2026-06-18-dreaming-url-enrichment-requirements.md)*

---

## Key Technical Decisions

- **Use `--json` for concordance output:** More reliable than parsing tab-separated stdout. JSON gives a structured array; count = `len(results)`, first URL = `results[0]["url"]`. `--limit 50` caps the query — exact total count isn't critical, the first URL is what matters.
- **Standalone tool with duplicated helpers:** `enrich_dreaming_urls.py` duplicates `get_env`, `run_cmd`, `get_sheets_service`, and `read_sheet` from `sheets_to_anki.py` rather than importing them. Tools are meant to be independently runnable; importing from a script named `sheets_to_anki.py` would create confusing coupling with no shared-module abstraction to justify it.
- **Append-mode log file:** Unlike `sheets_to_anki.py`'s per-run log files, this tool appends all runs to a single file (`dreaming_enrichment.log`), making it easier to audit a history of scheduled/invisible runs in one place.
- **Column E default, configurable:** `DREAMING_URL_COLUMN` env var mirrors the existing `ANKI_DONE_COL` convention.

---

## Implementation Units

### U1. Create `tools/enrich_dreaming_urls.py`

**Goal:** Core enrichment tool — reads the sheet, calls concordance for unenriched rows, writes URL or `no matches`, logs results.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None

**Files:**
- `tools/enrich_dreaming_urls.py` (new)

**Approach:**
- Load `.env` via `python-dotenv` and read: `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB` (default `Sheet1`), `ANKI_BACK_COL` (Spanish word column, default `B`), `ANKI_HEADER_ROW` (default `1`), `DREAMING_URL_COLUMN` (default `E`), `DREAMING_CLI_PATH` (default `dreaming-pp-cli`), `DREAMING_LOG_PATH` (default `.tmp/dreaming_enrichment.log`)
- Authenticate and read the sheet using the same `get_sheets_service()` / `read_sheet()` pattern as `sheets_to_anki.py` (duplicate, do not import)
- Write individual cells via `service.spreadsheets().values().update()` with `valueInputOption="USER_ENTERED"`, using the same cell-range format `'{tab}'!{col}{row}`
- For each data row: skip if the URL column cell is non-empty; otherwise call `run_cmd([cli_path, "concordance", spanish_word, "--json", "--limit", "50"])`
- Parse stdout as JSON; if the result array is non-empty, write `<results[0]["url"]> (<len(results)> matches)`; if empty, write `no matches`
- Handle `dreaming-pp-cli` not found (return code -1 / `FileNotFoundError` from `run_cmd`) with a printed warning and early exit before touching the sheet
- Track per-run counts: `enriched`, `no_matches`, `skipped`, `errors`
- Log: one line per error (`[timestamp] ERROR row N (<word>): <message>`), then the summary line (`[timestamp] Dreaming URL enrichment: N enriched, N no matches, N skipped, N error(s)`) — appended, not overwritten
- Accept `--dry-run` flag: print what would be written but skip sheet writes and log writes

**Patterns to follow:**
- `tools/sheets_to_anki.py`: `get_env()`, `run_cmd()`, `get_sheets_service()`, `read_sheet()`, column index resolution via `column_index_from_string()`, Windows Unicode fix (`sys.stdout.reconfigure`)

**Test scenarios:**
- Happy path: row with Spanish word, empty URL column, concordance returns hits → cell written as `https://... (N matches)`
- Idempotent skip: row already has a URL value → skipped, no sheet write, skipped count incremented
- No matches: concordance returns empty JSON array → cell written as `no matches`
- CLI not on PATH: `run_cmd` returns code -1 → prints warning, exits cleanly without touching the sheet
- Blank Spanish word: row with empty back column → skipped, no concordance call
- Dry run: no sheet writes, no log writes, console shows what would happen
- Log append: two consecutive runs each append their own summary line; file grows, prior lines preserved
- Error path: concordance subprocess fails for one word → error logged per-row, run continues for other rows, summary reflects error count

**Verification:** Running the tool against the live sheet populates the URL column correctly. A second run touches nothing. Log file shows the summary line.

---

### U2. Update `.env.example` with new variables

**Goal:** Document the three new config variables so project setup captures them.

**Requirements:** R1, R4

**Dependencies:** None

**Files:**
- `.env.example` (modify)

**Approach:** Append a commented section after the existing Anki variables:

```
# --- Dreaming URL Enrichment (tools/enrich_dreaming_urls.py) ---
# DREAMING_CLI_PATH=dreaming-pp-cli            # Default: dreaming-pp-cli (must be on PATH)
# DREAMING_URL_COLUMN=E                        # Default: E (sheet column for video URLs)
# DREAMING_LOG_PATH=.tmp/dreaming_enrichment.log  # Default shown; appended on each run
```

**Test scenarios:**
- Test expectation: none — configuration documentation only

**Verification:** `.env.example` shows the three variables with defaults and one-line descriptions matching the tool's behavior.

---

### U3. Update `workflows/sheets_to_anki.md`

**Goal:** Document the enrichment step as part of the sync workflow.

**Requirements:** R1 (workflow integration)

**Dependencies:** U1

**Files:**
- `workflows/sheets_to_anki.md` (modify)

**Approach:** Add a step after the card-creation section:

> **Dreaming URL Enrichment**
> Run `python tools/enrich_dreaming_urls.py` to populate the URL column for any words missing a Dreaming.com video link. This step is idempotent — already-enriched rows are skipped. Check `.tmp/dreaming_enrichment.log` for run summaries when running on a schedule.

**Test scenarios:**
- Test expectation: none — documentation only

**Verification:** The workflow doc shows the enrichment step in sequence after card creation.

---

## Scope Boundaries

**Out of scope:**
- Multiple URLs per cell
- Anki card field enrichment
- French vocabulary support
- Re-querying rows already marked `no matches`

**Deferred to follow-up work:**
- Shared helper module across tools (worth revisiting if a third tool is added)
- `--force` flag to re-enrich already-enriched rows

---

## Open Questions

- The JSON field name for the URL is assumed to be `"url"` based on the concordance command's Go struct. Confirm on first run; if different, the JSON parsing in U1 needs a one-line fix.
