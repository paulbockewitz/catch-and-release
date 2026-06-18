# Workflow: Vocab Sheet Spell-Check (Google Apps Script)

Auto-corrects spelling errors and missing accents in column A of the vocabulary sheet at the moment of entry, using the LanguageTool free REST API. Corrections happen in-place; the original value is preserved as a cell note.

---

## Script Files

| File | Purpose |
|---|---|
| `tools/vocab_spell_check.gs` | Main Apps Script — `handleEdit` trigger + `createTrigger` installer |
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

The manifest declares two OAuth scopes:
- `https://www.googleapis.com/auth/spreadsheets` — read and write sheet cells
- `https://www.googleapis.com/auth/script.external_request` — call LanguageTool via `UrlFetchApp`

Without the `external_request` scope, `UrlFetchApp.fetch()` silently fails under an installable trigger.

### Step 4: Paste the script

1. Click `Code.gs` (or any existing `.gs` file) in the file list.
2. Replace all existing content with the contents of `tools/vocab_spell_check.gs` from this repo.
3. Save.

### Step 5: Register the installable trigger

> **Why installable, not simple?** Google Apps Script's simple `onEdit` trigger runs without authorization and cannot make external HTTP calls. The installable trigger runs as you (the installing user) and can call `UrlFetchApp`.

1. In the Script Editor function dropdown (top of editor), select **`createTrigger`**.
2. Click **Run**.
3. A permission dialog will appear — click **Review Permissions**, then **Allow**. Grant both the spreadsheet and external request scopes.
4. The trigger is now registered. You can verify it under **Triggers** (clock icon in the left sidebar) — you should see `handleEdit` listed with event type **On edit**.

`createTrigger` guards against duplicates: running it again is safe and will log "Trigger already exists" without creating a second trigger.

### Step 6: Verify it works

1. Return to the vocabulary sheet.
2. Type `caida` in any empty cell in column A and press Enter.
3. Within 1–2 seconds the cell should update to `caída` and show a small triangle in the corner (hover to see the original value `caida` in the note tooltip).

---

## How It Works

- **Single-cell edit:** every column A edit fires `handleEdit`, which sends the cell text to LanguageTool and applies the first replacement suggestion for each spelling match.
- **Bulk paste:** if you paste multiple rows into column A at once, only the first row is corrected. Remaining rows are left unchanged to stay within the free-tier rate limit (20 req/min).
- **No grammar corrections:** only matches where `rule.issueType === "misspelling"` are applied. Grammar, style, and punctuation suggestions are ignored.
- **Low confidence guard:** if LanguageTool's language detector confidence is below 0.5 (common for single short words), the cell is left unchanged and the note is set to `"LT: low confidence"`. Try a longer word or phrase if this fires unexpectedly.
- **Cell note:** when a correction fires, the original value is saved as a cell note so you can verify or undo without relying on Ctrl+Z.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Trigger not firing at all | Go to Extensions → Apps Script → Triggers (clock icon). Confirm `handleEdit` appears with event "From spreadsheet / On edit". If missing, run `createTrigger()` again. |
| `UrlFetchApp` permission error in execution log | The trigger was registered before the manifest was updated, or the function was named `onEdit` (simple trigger). Delete the trigger, update `appsscript.json`, rename the function to `handleEdit`, save, then run `createTrigger()` again. |
| Cell note reads "LT: low confidence" | LanguageTool wasn't sure which language the input was. Try typing a full word or short phrase instead of a single character. |
| Correction fired but seems wrong | Check the cell note for the original. Press Ctrl+Z to undo if the correction was incorrect; LanguageTool occasionally suggests the wrong replacement for highly ambiguous input. |
| Bulk-pasted rows not corrected | By design — only the first row of a paste is corrected. Correct the remaining rows individually by clicking into each cell and pressing Enter. |

---

## Rate Limits

LanguageTool free tier: 20 requests/minute, 75 KB/minute, 20 KB per request. Typing vocabulary words one at a time is well within these limits. If you paste many rows quickly and the first rows stop being corrected, wait a minute before continuing.

---

## Updating the Script

The `tools/vocab_spell_check.gs` and `tools/appsscript.json` files in this repo are the canonical source. To deploy an update:

1. Open Extensions → Apps Script.
2. Replace the Script Editor content with the updated file contents from `tools/`.
3. Save. No need to re-run `createTrigger()` — the trigger remains registered.
