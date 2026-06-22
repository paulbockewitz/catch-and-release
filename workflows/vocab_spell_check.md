# Workflow: Vocab Sheet Spell-Check (Google Apps Script)

Auto-corrects spelling errors and missing accents in column A of the vocabulary sheet at the moment of entry. Works with both Spanish and English input — detects the language automatically, writes it to column C, and writes a GOOGLETRANSLATE formula to column B so both languages are populated without manual entry.

---

## Script Files

| File | Purpose |
|---|---|
| `tools/vocab_spell_check.gs` | Main Apps Script — `handleEdit` trigger, `createTrigger` installer, `setupTranslationFormulas` backfill |
| `tools/appsscript.json` | OAuth scope manifest — required to authorize `UrlFetchApp` calls |

---

## One-Time Setup

### Step 1: Open the Script Editor

1. Open the vocabulary Google Sheet.
2. Go to **Extensions → Apps Script**.

### Step 2: Enable the manifest editor

1. In the Script Editor, click the gear icon (**Project Settings**).
2. Check **"Show `appsscript.json` manifest file in editor"**.
3. The `appsscript.json` file will now appear in the file list on the left.

### Step 3: Paste the manifest

1. Click `appsscript.json` in the file list.
2. Replace all existing content with the contents of `tools/appsscript.json` from this repo.
3. Save (Ctrl+S or the floppy disk icon).

The manifest declares three OAuth scopes:
- `https://www.googleapis.com/auth/spreadsheets` — read and write sheet cells
- `https://www.googleapis.com/auth/script.external_request` — call LanguageTool via `UrlFetchApp`
- `https://www.googleapis.com/auth/script.scriptapp` — register and read installable triggers via `ScriptApp`

Without `external_request`, `UrlFetchApp.fetch()` silently fails. Without `script.scriptapp`, `createTrigger()` throws a permissions error.

### Step 4: Paste the script

1. Click `Code.gs` (or any existing `.gs` file) in the file list.
2. Replace all existing content with the contents of `tools/vocab_spell_check.gs` from this repo.
3. Save.

### Step 5: Register the installable trigger

> **Why installable, not simple?** Google Apps Script's simple `onEdit` trigger runs without authorization and cannot make external HTTP calls. The installable trigger runs as you (the installing user) and can call `UrlFetchApp`.

1. In the Script Editor function dropdown (top of editor), select **`createTrigger`**.
2. Click **Run**.
3. A permission dialog will appear — click **Review Permissions**, then **Allow**.
4. The trigger is now registered. Verify under **Triggers** (clock icon in the left sidebar) — you should see `handleEdit` listed with event type **On edit**.

`createTrigger` guards against duplicates: running it again is safe and will log "Trigger already exists" without creating a second trigger.

### Step 6: Backfill existing rows

> **Skip this step if the sheet is empty or all rows were entered after deploying the new script.**

For rows that already exist in the sheet, column B may be empty (no GOOGLETRANSLATE formula yet). Run `setupTranslationFormulas` once to backfill them:

1. In the function dropdown, select **`setupTranslationFormulas`**.
2. Click **Run**.

This writes the GOOGLETRANSLATE formula to column B for every row where column A is non-empty and column B is currently empty. Rows where column B already has a value (user-typed translation) are left unchanged.

### Step 7: Verify it works

1. Return to the vocabulary sheet.
2. Type a **Spanish word with a missing accent** (e.g. `caida`) in any empty cell in column A and press Enter.
   - Column A should update to `caída` within 1–2 seconds, with a small triangle indicating the original is saved as a cell note.
   - Column C should show `es`.
   - Column B should show the English translation (e.g. `fall`).
3. Type an **English word** (e.g. `however`) in another column A cell.
   - Column A stays `however` (no correction needed).
   - Column C should show `en`.
   - Column B should show the Spanish translation (e.g. `sin embargo`).

---

## How It Works

### Language detection

On every column A edit, the trigger runs two LanguageTool API calls in parallel:

1. If the input contains Spanish diacritics (`ñ á é í ó ú ü Á É Í Ó Ú Ü ¿ ¡`), it calls only LT `es` (unambiguously Spanish — skip the English call).
2. Otherwise, it calls both LT `es` and LT `en-US` and applies the zero-match oracle:

| LT `es` flags | LT `en-US` flags | Result |
|---|---|---|
| 0 issues | > 0 issues | Spanish (`es`) |
| > 0 issues | 0 issues | Check edit distance of es correction: ≤ 1 → `es` (accent error), > 1 → `en` |
| 0 issues | 0 issues | Spanish (`es`) — tiebreaker; "no" and similar ambiguous words default to Spanish |
| > 0 issues | > 0 issues | Whichever language's correction is closer (edit distance) wins |

The detected language is written to **column C** via `setValue()`.

### Translation formula

After writing column C, the trigger writes the following formula to **column B** if column B is currently empty:

```
=IF(An="","",IFERROR(GOOGLETRANSLATE(An,Cn,IF(Cn="es","en","es")),""))
```

- `IF(An="","","")` — keeps column B empty when column A is empty
- `IFERROR(...)` — suppresses `#N/A` for very short or unsupported strings
- `IF(Cn="es","en","es")` — translates Spanish→English when detected Spanish; English→Spanish otherwise

If column B already has a value (user-typed), it is left unchanged.

### Spelling correction

After writing column C, the trigger applies any spelling or accent corrections from the winning LT result:

- **Bulk paste:** if multiple rows are pasted at once, only the first row is corrected to stay within the free-tier rate limit.
- **Accepted match types:** `issueType === "misspelling"` (wrong letters) and `issueType === "typographical"` (missing/wrong accent).
- **Rejected match types:** grammar, style, and punctuation — excluded both by the match filter and by `disabledCategories` in the API call.
- **Shortening guard:** corrections that shorten the matched span are rejected. This prevents LT `es` from truncating Spanish words it misidentifies (e.g. "lucido" → "lucid").
- **Case preservation:** if the original started lowercase but the correction is capitalized (LT treats single words as sentence-starts), the first character is lowercased back.
- **Original saved:** when a correction fires, the original value is saved as a cell note for review or undo.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Trigger not firing at all | Go to Extensions → Apps Script → Triggers (clock icon). Confirm `handleEdit` appears with event "From spreadsheet / On edit". If missing, run `createTrigger()` again. |
| `UrlFetchApp` permission error in execution log | The trigger was registered before the manifest was updated, or the function was named `onEdit` (simple trigger). Delete the trigger, update `appsscript.json`, rename to `handleEdit`, save, then run `createTrigger()` again. |
| Column C shows wrong language | For Spanish words with missing accents (e.g. "caida"), the detection uses an edit-distance check — if LT `es` suggests an accent fix at edit distance ≤ 1, it's treated as Spanish. Very short English words that happen to be one edit away from a Spanish word may occasionally be misclassified; this is a known edge case. |
| Column B formula not appearing | Column B already has a value (user-typed) that the trigger won't overwrite. If you want the auto-translation, clear column B manually first, then re-edit column A. For existing empty rows not yet touched by the trigger, run `setupTranslationFormulas()`. |
| Translation in column B shows `#N/A` | GOOGLETRANSLATE occasionally returns `#N/A` for very short or ambiguous strings. The IFERROR wrapper converts this to an empty string. |
| Correction fired but seems wrong | Check the cell note for the original. Press Ctrl+Z to undo if the correction was incorrect; LanguageTool occasionally suggests the wrong replacement for highly ambiguous input. |
| Bulk-pasted rows not corrected | By design — only the first row of a paste is corrected. Correct the remaining rows individually by clicking into each cell and pressing Enter. |
| `setupTranslationFormulas` not listed in dropdown | The updated script hasn't been pasted yet. Complete Step 4 (paste the script) and save before running this function. |

---

## Rate Limits

LanguageTool free tier: 20 requests/minute, 75 KB/minute, 20 KB per request.

Each column A edit makes **2 LT API calls** (one for `es`, one for `en-US`), except for words with Spanish diacritics which make 1 call. At personal vocabulary volumes this is well within limits. If corrections stop firing after rapid entry, wait a minute before continuing.

---

## Updating the Script

The `tools/vocab_spell_check.gs` and `tools/appsscript.json` files in this repo are the canonical source. To deploy an update:

1. Open Extensions → Apps Script.
2. Replace the Script Editor content with the updated file contents from `tools/`.
3. Save. No need to re-run `createTrigger()` — the trigger remains registered.
