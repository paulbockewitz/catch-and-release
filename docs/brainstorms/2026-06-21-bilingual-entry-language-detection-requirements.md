---
date: 2026-06-21
topic: bilingual-entry-language-detection
---

# Bilingual Entry Language Detection

## Summary

Replace the unreliable `DETECTLANGUAGE` formula in the Vocab Sheet's language column (col C) with GAS-driven detection that writes a reliable "es" or "en" value on each word entry, and add a `GOOGLETRANSLATE` formula to col B so the user can type a word or phrase in either English or Spanish and get both languages filled in automatically.

---

## Problem Frame

The Vocab Sheet uses `=DETECTLANGUAGE(A)` in column C to identify whether an entered word is Spanish or English. `DETECTLANGUAGE` is a generic 100-language classifier. For short words it frequently returns non-Spanish codes — Italian, Romanian, Croatian, Portuguese — because short common words appear across multiple Romance languages. "pero" looks like Croatian; "hace" looks like Romanian; "como" matches several languages at once. The misclassification routes the Dreaming URL enrichment to the wrong column and forces the user to manually enter both the Spanish word and the English translation on every row.

The user's workflow is bidirectional: they type either Spanish vocabulary heard while watching Dreaming Spanish content, or English words they want to look up. The sheet should handle either direction without requiring the user to know or care which column is "the Spanish column."

---

## Column Structure Before / After

| Column | Before | After |
|--------|--------|-------|
| A | User input (Spanish assumed) | User input (Spanish **or** English) |
| B | User-entered English translation | `=GOOGLETRANSLATE(A, C, ...)` — auto-populated |
| C | `=DETECTLANGUAGE(A)` — unreliable | GAS-written "es" or "en" — reliable |

---

## Key Decisions

**Language scope: English and Spanish only.** Restricting to two languages makes the detection problem tractable and matches the user's stated use case. Any non-es/non-en result from any detection mechanism must resolve to one of these two values, never left as a third-language code.

**Ambiguous word tiebreaker: default to Spanish.** Words that LanguageTool accepts as valid in both es and en (e.g., "no", "con", "me") default to "es". In a Spanish vocabulary learning context, an ambiguous word is almost always being added as Spanish. The col B translation makes the outcome visible; if wrong, the user edits col C manually.

**GAS is the detection authority, not DETECTLANGUAGE.** The `vocab_spell_check.gs` `onEdit` trigger already calls LanguageTool with language-specific endpoints as part of spell-check. LanguageTool's response carries a reliable signal: it returns zero matches for words it accepts as valid in the target language, and returns TYPO/misspelling matches for words it does not recognize. This signal is symmetric — it works equally well for English and Spanish inputs — making it a more reliable oracle than DETECTLANGUAGE for the short words that fail most often. The existing DETECTLANGUAGE formula in col C acts as a bootstrap value for rows not yet touched by GAS; GAS overwrites it with a plain text value on first edit.

**Translation is formula-driven.** Col B gets a `GOOGLETRANSLATE` formula that reads col C for direction. This keeps the translation always current and requires no additional GAS code or API calls. When GAS later writes a corrected language to col C, the col B formula re-evaluates automatically.

---

## Requirements

**Detection**

- R1. When a word or phrase is entered in col A, `vocab_spell_check.gs` must determine whether it is Spanish or English and write "es" or "en" to col C.
- R2. Detection must be accurate for correctly spelled words in both languages — not only words with spelling errors that trigger LT suggestions.
- R3. Words containing Spanish diacritics (ñ, á, é, í, ó, ú, ü and uppercase equivalents, ¿, ¡) must be classified "es" without relying on DETECTLANGUAGE.
- R4. When the LanguageTool response indicates the word is valid in one language (zero matching issues) but flagged in the other, that language wins — no bias toward either language in this case.
- R5. Genuinely ambiguous words valid in both LT es and LT en must have a defined fallback behavior rather than failing silently or producing an empty col C. (See Outstanding Questions for the options.)
- R6. When col A is empty, col C must not contain "es" or "en" — it must be empty or preserve the DETECTLANGUAGE formula result.

**Translation**

- R7. Col B must contain a formula that auto-populates with the translation of col A into the opposite language, using col C to determine direction.
- R8. When col C is "es", col B translates Spanish → English. When col C is "en", col B translates English → Spanish.
- R9. When col A is empty, col B must remain empty.

**Integration**

- R10. `enrich_dreaming_urls.py` routing must continue without changes: col C "es" queries col A; any other value queries col B.
- R11. `sheets_to_anki.py` must continue without changes, reading col A (front) and col B (back).
- R12. Spell-check correction behavior must be unchanged — GAS still corrects accents and spelling in col A in addition to writing col C.

---

## Key Flows

- F1. **Spanish word entry**
  - **Trigger:** User types a Spanish word in col A.
  - **Steps:** DETECTLANGUAGE recalculates col C (initial, may be wrong); GOOGLETRANSLATE recalculates col B using initial col C; GAS fires, calls LT endpoints, finds the word valid in es and flagged in en; GAS writes "es" to col C; col B re-evaluates and shows English translation.
  - **Outcome:** col A = corrected Spanish word; col C = "es"; col B = English translation.

- F2. **English word entry**
  - **Trigger:** User types an English word in col A.
  - **Steps:** Same as F1 but GAS finds the word valid in en and flagged in es; writes "en" to col C; col B re-evaluates to show Spanish translation.
  - **Outcome:** col A = corrected English word; col C = "en"; col B = Spanish translation.

- F3. **Ambiguous word entry** (e.g., "no", "a", "con")
  - **Trigger:** User types a word that LT accepts as valid in both languages.
  - **Steps:** GAS finds zero-match responses from both LT es and LT en; applies the defined fallback (see Outstanding Questions); writes "es" or "en" to col C.
  - **Outcome:** col C set per fallback; col B shows the corresponding translation.

---

## Acceptance Examples

- AE1. `"pero"` (correctly spelled Spanish word, no diacritics) → col C = "es", col B = "but". LT en-US flags it as unknown; LT es returns 0 matches.
- AE2. `"however"` → col C = "en", col B = "sin embargo". LT es flags it; LT en-US returns 0 matches.
- AE3. `"caida"` (Spanish typo for "caída") → GAS corrects col A to "caída"; col C = "es"; col B = "fall".
- AE4. `"ultimamente"` → GAS corrects col A to "últimamente"; col C = "es"; col B = "lately".
- AE5. `"casa"` → col C = "es", col B = "house". Even though DETECTLANGUAGE may return "it" (Italian), GAS detection wins.
- AE6. `"no"` → fallback behavior fires (tiebreaker defined in implementation); col C = "es" or "en"; col B = corresponding translation.
- AE7. Empty col A → col C and col B remain empty.

---

## Scope Boundaries

- Languages other than English and Spanish are not supported. Any third-language result from DETECTLANGUAGE or LT must be resolved to "es" or "en" — never left as an unexpected code that breaks enrichment routing.
- Manual col C overrides are not a designed feature. If the user types "es" or "en" directly in col C, GAS overwrites it on the next col A edit.
- Backfilling existing rows that have never triggered the new GAS logic is deferred. Existing DETECTLANGUAGE formula values remain until each row is re-edited in col A.
- GOOGLETRANSLATE output quality for multi-word phrases is accepted as-is. The sheet uses the formula's result; no custom post-processing of translation output is required.

---

## Dependencies / Assumptions

- `GOOGLETRANSLATE` is available as a built-in Sheets function without additional auth.
- LanguageTool's free API returns a TYPO or misspelling match for words it does not recognize as valid in the target language. Confirmed in existing code — `vocab_spell_check.gs` already filters on `issueType === 'misspelling' || issueType === 'typographical'`.
- GAS `onEdit` writes to col C using `Range.setValue()`. This should trigger the col B GOOGLETRANSLATE formula to re-evaluate, giving the correct translation after GAS completes. Planning must verify this re-evaluation timing.
- The existing LT `language=auto` call in the current GAS does NOT call both es and en for every word — the dual es/en calls only fire in the fallback branch (unexpected or low-confidence auto-detect). Planning must decide whether to restructure the LT call order so language detection data is available in all branches, not just the fallback.

---

## Outstanding Questions

**Deferred to planning:**

- OQ2. Exact LT response signal for "valid in this language": likely `matches.length === 0` after filtering for misspelling/typographical issues, but planning must verify LT does not silently return 0 matches for words it has no entry for (some rare words may simply not be in the corpus).
- OQ3. Whether to wrap col B formula in `IFERROR` to suppress `#N/A` for very short or unsupported strings.
- OQ4. Whether GAS should call both LT es and LT en for every word (restructuring the current conditional call order) or only in the branches where it's needed for language detection.
- OQ5. Formula syntax and cell range for col B given the need to handle the GOOGLETRANSLATE → col C timing sequence (whether the initial DETECTLANGUAGE value in col C is "good enough" for a first pass, or whether the translation should only show after GAS writes the confirmed language).

---

## Sources

- `tools/vocab_spell_check.gs` — existing GAS; the `callLanguageTool`, `firstCorrectedText`, and `handleEdit` functions are the direct targets of the detection change.
- `tools/enrich_dreaming_urls.py` — reads col C at `lang_col` (line 196); routing logic at lines 252–257.
- `docs/brainstorms/2026-06-18-vocab-sheet-spell-check-requirements.md` — prior brainstorm for the spell-check feature; language detection was part of that scope but not the primary focus.
- Grounding dossier: `/tmp/compound-engineering/ce-brainstorm/lang-detect-001/grounding.md`
