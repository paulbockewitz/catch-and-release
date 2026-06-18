---
date: 2026-06-18
topic: vocab-sheet-spell-check
---

# Vocab Sheet Spell-Check

## Summary

A Google Apps Script attached to the vocabulary Google Sheet that auto-corrects spelling errors in column A as the user types — covering both missing accents (`caida` → `caída`) and full misspellings (`covencion` → `convención`) — so that words reach Anki cards in their correct form without a separate correction step.

---

## Problem Frame

Misspelled words entered in column A flow to Anki card fronts unchanged. The sync script (`tools/sheets_to_anki.py`) passes column A values verbatim to the CLI with only `.strip()` applied — no normalization, no correction. The June 2026 run log already has committed cards with stripped accents (`caída` → `caida`, `últimamente` → `ultimamente`) and transposition errors (`convención` → `covencion`). Because the sync marks rows done with a checkmark, correcting these cards requires manual Anki intervention after the fact.

---

## Key Decisions

- **Apps Script over a Python WAT tool.** The correction fires at the moment of entry, before the word is ever read by the sync. A Python tool would require a separate preprocessing run and would still miss the entry-time window the user prefers.

- **Full spell-check scope, not just accent restoration.** The motivating example (`covencion`) has a transposed letter in addition to a missing accent. An accent-only lookup would not catch it. LanguageTool handles both cases with the same API call.

- **LanguageTool free REST API over an embedded word list.** A language learner's vocabulary is unpredictable — uncommon words and phrases not in a fixed list would be silently skipped. LanguageTool covers the full Spanish and English spelling rule sets without requiring an API key.

- **Bidirectional correction (Spanish and English).** LanguageTool auto-detects language per entry. English words in column A are spell-checked as a confirmed side effect — not a separate feature, just the natural behavior of the chosen API.

---

## Requirements

**Entry trigger**

- R1. The script registers an `onEdit` trigger on the vocabulary sheet, column A only.
- R2. The trigger fires on every cell edit in column A, including single-character changes.
- R3. Empty cells are skipped without an API call.

**Correction behavior**

- R4. On trigger, the script sends the edited cell's value to the LanguageTool free REST API with language set to `auto`.
- R5. If the API returns one or more spelling correction matches, the script replaces the cell value with the corrected text.
- R6. If the API returns no spelling corrections, the cell is left unchanged.
- R7. Grammar and style suggestions from LanguageTool are ignored — spelling matches only.
- R8. Multi-word phrases are sent and corrected as a whole unit (LanguageTool handles phrase context).

**Scope constraints**

- R9. The script writes only to the column A cell that triggered the edit; columns B, C, and D are not modified.
- R10. The script does not reprocess existing rows; correction applies only at the moment of entry.

---

## Key Flows

- F1. **Accent correction** — User types `anfitrion` into a column A cell and commits.
  - **Trigger:** `onEdit` fires on a column A cell.
  - **Steps:** Script sends `"anfitrion"` to LanguageTool API → API returns correction `"anfitrión"` → script overwrites the cell.
  - **Outcome:** Cell reads `"anfitrión"` before the next sync reads it.

- F2. **Full misspelling correction** — User types `covencion`.
  - **Trigger:** `onEdit` fires on a column A cell.
  - **Steps:** Script sends `"covencion"` → API returns `"convención"` → script overwrites.
  - **Outcome:** Cell reads `"convención"`.

- F3. **English typo** — User types `distrubute`.
  - **Trigger:** `onEdit` fires on a column A cell.
  - **Steps:** Script sends `"distrubute"` → API detects English, returns `"distribute"` → script overwrites.
  - **Outcome:** Cell reads `"distribute"`.

- F4. **No correction needed** — User types a correctly spelled word.
  - **Trigger:** `onEdit` fires on a column A cell.
  - **Steps:** Script calls API → API returns no spelling corrections → no change.
  - **Outcome:** Cell value unchanged.

---

## Acceptance Examples

- AE1. `caida` → `caída` (missing accent, common Spanish word).
- AE2. `covencion` → `convención` (transposition + missing accent).
- AE3. `ultimamente` → `últimamente` (missing accent on a multi-syllable word).
- AE4. `distrubute` → `distribute` (English transposition).
- AE5. `skydiving` → no change (correctly spelled English word).
- AE6. `Has oido de la ministra` → `Has oído de la ministra` (accent in a phrase).
- AE7. Empty cell → no API call, no change.

---

## Scope Boundaries

- Already-synced rows (column D contains `✓`) are not backfilled — Anki cards committed before this script exists retain their original spelling.
- Grammar, style, and punctuation suggestions from LanguageTool are not applied.
- No changes to `tools/sheets_to_anki.py` or any Python WAT tool.

---

## Dependencies / Assumptions

- LanguageTool free REST API (`https://api.languagetool.org/v2/check`) is reachable from Google Apps Script execution environment; no authentication required for standard personal usage.
- Free tier allows approximately 20 requests/minute — sufficient for one-at-a-time manual entry; pasting many rows at once may hit the rate limit.

---

## Outstanding Questions

**Deferred to Planning**

- How to handle the rate limit when a user pastes multiple rows into column A simultaneously (options: skip excess cells, queue with delay, or process only the edited cell and ignore bulk paste).
- Whether to add a cell note or comment showing the original value when a correction fires, so the user can verify or undo without relying on Ctrl+Z.
