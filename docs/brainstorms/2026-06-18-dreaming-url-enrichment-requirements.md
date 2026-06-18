---
title: Dreaming.com URL Enrichment for Vocabulary Sheet
date: 2026-06-18
status: draft
---

# Dreaming.com URL Enrichment for Vocabulary Sheet

## Outcome

After each vocabulary sync run, every Spanish word in the sheet that has at least one concordance hit in the dreaming-pp-cli gains a clickable Dreaming.com video URL in a dedicated sheet column. The URL gives a direct route into comprehensible-input context for that word during study.

## Background

The existing `sheets_to_anki.py` sync reads Spanish words from the vocabulary Google Sheet and creates Anki cards via the AnkiWeb CLI. The dreaming-pp-cli already has a `concordance` command that searches video transcripts for a word/phrase and returns hits with video URLs (via `VideoWebURL()`, which constructs `https://app.dreaming.com/spanish/watch?id=<id>`). These two systems have never been connected.

## What We're Building

A new enrichment step — implemented as a standalone tool `tools/enrich_dreaming_urls.py` — that runs automatically as part of the `sheets_to_anki` workflow after cards are created.

**Per-row behavior:**
- If the URL column already has a value (URL or `no matches`): skip. The step is idempotent.
- If the URL column is empty: run `dreaming-pp-cli concordance <spanish_word>`, take the first hit, and write `<url> (<N> matches)` to the URL column.
- If concordance returns zero hits: write `no matches` to the URL column.
- No fuzzy or prefix fallback — exact match only. A word marked `no matches` stays that way.

**Output format (one cell):**
```
https://app.dreaming.com/spanish/watch?id=abc123 (3 matches)
```

## Scope Boundaries

**Out of scope:**
- Multiple URLs per cell
- Writing URLs to Anki card fields
- French vocabulary (Spanish only, even though the CLI supports French)
- Retroactively re-querying words already marked `no matches`

## Sheet Column Assignment

The URL column is the first empty column after the existing checkmark column (currently column D). This should be made configurable via `.env` as `DREAMING_URL_COLUMN` so it survives future sheet layout changes.

## Workflow Integration

`workflows/sheets_to_anki.md` is updated to add a step after card creation:

> **Step N — Dreaming URL Enrichment**
> Run `python tools/enrich_dreaming_urls.py` to populate the URL column for any words missing enrichment. This step is safe to re-run; already-enriched rows are skipped.

## Success Criteria

- After sync, every Spanish word with at least one concordance hit shows a URL in the sheet column.
- Words with no concordance hits show `no matches`.
- Re-running the sync does not overwrite or duplicate existing values.
- The tool runs without errors when `dreaming-pp-cli` is not installed (graceful skip with a warning).

## Assumptions

- Column A = English (front), Column B = Spanish (back), Column D = done checkmark. The URL column is E unless `DREAMING_URL_COLUMN` overrides it.
- `dreaming-pp-cli` is available on `PATH` on the machine running the sync (same machine as the rest of the workflow).
- Concordance output format is stable enough to parse the first video URL via stdout.

## Logging

The tool writes a run summary to a logfile (appended, not overwritten) since the sync may run scheduled or invisibly. Summary format:

```
[2026-06-18 14:32:01] Dreaming URL enrichment: 12 enriched, 3 no matches, 45 skipped
```

Log path is configurable via `.env` as `DREAMING_LOG_PATH`, defaulting to `.tmp/dreaming_enrichment.log`. Errors (e.g., concordance subprocess failure for a specific word) are logged per-row before the summary line.
