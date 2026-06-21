---
title: Spanish Accent Guard English-Bailout Regression
date: 2026-06-21
category: docs/solutions/logic-errors
module: vocab_spell_check
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "Spanish accent corrections (e.g., ultimamente to ultmamente) silently skipped with no error"
  - "English LanguageTool returns no match for valid Spanish words, causing early return before Spanish check runs"
  - "Accent-only fixes (edit distance 1) rejected by same guard intended to block English truncations (edit distance 8+)"
root_cause: logic_error
resolution_type: code_fix
tags:
  - spell-check
  - language-detection
  - languagetool
  - edit-distance
  - google-apps-script
  - spanish-accents
---

# Spanish Accent Guard English-Bailout Regression

## Problem

The `vocab_spell_check.gs` `onEdit` trigger failed to apply Spanish accent corrections (e.g., "ultimamente" to "últimamente") when LanguageTool's English API returned no suggestion for the input word. A guard clause added to prevent English from truncating Spanish words was too broad — it bailed out of the entire correction flow whenever English had nothing to say, even when a clear accent fix was available.

## Symptoms

- Typing a Spanish word with a missing accent mark in column A produces no correction, even when LanguageTool's `es` endpoint returns the correct accented form.
- The failure is silent: no error, no partial edit — the cell is left unchanged.
- Specifically affects words where English LanguageTool returns zero suggestions — common for Spanish-only vocabulary like "ultimamente", "facilmente", "comunmente".
- The code comment itself cited "ultimamente" as an example that *should* be corrected, making the regression self-documenting once noticed.

## What Didn't Work

**Prior iteration history** (session history): The spell-check feature went through five failed approaches before the regression occurred:

1. `language=auto` alone: unreliable for single words. "ultimamente" was returned as language `"it"` (Italian), so no correction fired.
2. Confidence threshold as sole guard (`confidence < 0.5` bail): blocked valid accent corrections for short ambiguous words where LanguageTool hedges.
3. Filtering only `issueType: "misspelling"`: missing accents are classified as `"typographical"` by LanguageTool, silently dropping the entire class the feature was built for.
4. ES-only retry without EN parallel call: correctly fixed Spanish words but misfired on English typos (`distrubute → distribuye` instead of `distribute`). Fix: call both `es` and `en-US`, pick by edit distance.
5. **The regression itself**: step 4's fix introduced `if (!enFirst) return` to avoid calling `closerResult()` without an English candidate. The reasoning ("if English can't correct it, we have no basis for comparison") was wrong — it treated "English has no correction" as one undifferentiated case when it actually covers two opposite situations:
   - Valid English word, nothing to fix → bail is correct
   - Spanish-only word, English simply has nothing to say → bail discards the legitimate accent fix

```javascript
// The failing guard — bails even when a clear Spanish accent fix is available
if (!enFirst) return;
```

## Solution

**Primary fix — English-bailout guard in `vocab_spell_check.gs`:**

```javascript
// Before
if (!enFirst) return;

// After
if (!enFirst) {
  // English has no correction. Could be valid English (bail) or a Spanish word
  // with only an accent error (apply). Accent fixes are edit distance <= 1;
  // false-positive Spanish "corrections" of English words are much farther away.
  // e.g. "imbalance" -> "invadanse" (d~8) should bail; "ultimamente" -> "ultmamente" (d=1) should apply.
  if (!esFirst || editDistance(originalText, esFirst) > 1) return;
  result = esResult;
} else {
  var chosen = closerResult(originalText, esResult, enResult);
  if (chosen) { result = chosen; } else { return; }
}
```

**Secondary fix — `firstCorrectedText` length filter:**

`firstCorrectedText()` is used to compute edit-distance candidates but was missing the shrinking-replacement guard present in `spellingMatches`, making the comparison measure suggestions that would never be applied:

```javascript
// Before — missing the length guard
var matches = (result.matches || []).filter(function(m) {
  return m.rule &&
         (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
         m.replacements && m.replacements.length > 0;
});

// After — consistent with spellingMatches
var matches = (result.matches || []).filter(function(m) {
  return m.rule &&
         (m.rule.issueType === 'misspelling' || m.rule.issueType === 'typographical') &&
         m.replacements && m.replacements.length > 0 &&
         m.replacements[0].value.length >= m.length;  // reject shrinking corrections
});
```

**Related reliability fixes in `enrich_dreaming_urls.py`** (fixed in the same code review pass):
- HYPERLINK formula injection: escape double-quotes with `.replace('"', '""')` (Sheets escape sequence) before embedding values in `=HYPERLINK()`.
- No subprocess timeout: `subprocess.run()` now includes `timeout=30` + `except subprocess.TimeoutExpired`.
- Unhandled flush_writes exception: final `batchUpdate` wrapped in try/except; logs the error and calls `sys.exit(1)`.
- CLI exits 0 on not-found: binary-not-found path changed from `sys.exit(0)` to `sys.exit(1)`.

## Why This Works

The edit-distance discriminator correctly separates the two "no English correction" cases because the LanguageTool suggestions for each case have structurally different distances from the original:

- **Accent fix**: changes exactly one character (the accent mark is added or swapped). Edit distance = 1. This is the only kind of fix LanguageTool makes to a correctly-spelled Spanish word missing its tilde.
- **False-positive Spanish correction of an English word**: produces a phonetically or morphologically distant Spanish word. "imbalance" to "invádanse" is approximately 8 character operations. These are always well above 1.

The threshold `> 1` cleanly separates the two populations without any language-identity heuristic.

`firstCorrectedText` must carry the same length guard as `spellingMatches` because it provides the edit-distance candidate used in `closerResult()`. If `firstCorrectedText` returns a shrinking correction that `spellingMatches` would reject, the comparison measures a ghost — a candidate that would never be applied. Keeping filters identical ensures the comparison reflects what would actually happen.

## Prevention

**Language detection branching:** Test each branch of a multi-language detection flow independently. "English has a correction" and "English has no correction" are behaviorally distinct and need separate test cases. The common failure mode is writing a guard for one branch that silently swallows the other. Key test cases: "ultimamente" (no English correction, accent fix should apply) and "imbalance" (no English correction, Spanish bailout is correct).

**Edit-distance as a discriminator:** When two APIs return suggestions for the same input with different intent (accent fix vs. semantic rewrite), edit distance is a reliable discriminator. Document the threshold and rationale inline — accent = 1 edit, semantic rewrite = many edits — so the next reader can judge edge cases rather than treating the threshold as an arbitrary magic number.

**Filter parity between paired functions:** When two functions in the same pipeline filter the same underlying data, keep their filter predicates identical or document explicitly why they differ. Divergence between `firstCorrectedText` and `spellingMatches` meant the comparison could measure a suggestion the application pipeline would reject.

**Formula string construction:** Any value embedded in a spreadsheet formula string must be escaped for that formula's quoting rules. In Google Sheets, double-quotes inside a string literal are escaped by doubling them (`"` to `""`). Apply this unconditionally — never assume external values are quote-free. Note: `valueInputOption="USER_ENTERED"` causes Sheets to evaluate formula-shaped strings; this is intentional for `=HYPERLINK()` but requires escaping all embedded values.

**Subprocess reliability:** Every `subprocess.run()` call against an external CLI should include `timeout=` (30 seconds is a reasonable default) and `except subprocess.TimeoutExpired` handling. Always exit non-zero (1) when the binary is not found — exit 0 causes callers to proceed as if the tool is available. Wrap the final write in try/except and log before exiting so the run failure is diagnosable.

## Related Issues

- Plan: [docs/plans/2026-06-18-001-feat-vocab-sheet-spell-check-plan.md](docs/plans/2026-06-18-001-feat-vocab-sheet-spell-check-plan.md) — U1 steps 6-7 specify the confidence guard and misspelling filter adjacent to where the regression lived. The plan predates the edit-distance discriminator; the new guard logic is not reflected there.
- Note for [docs/plans/2026-06-18-002-feat-dreaming-url-enrichment-plan.md](docs/plans/2026-06-18-002-feat-dreaming-url-enrichment-plan.md) — U1 specifies `valueInputOption="USER_ENTERED"` without noting the formula-escaping requirement; any new tool using `USER_ENTERED` with formula-like strings must apply the `"` to `""` escape.
