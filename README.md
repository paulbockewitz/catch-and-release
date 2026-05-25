# Catch and Release

A workflow for people learning a new language.  Frequently new words and phrases are discovered and forgotten.  This can create frustration and hinder learning.  Catch and release sets up the learner for success by using Google Sheets and the ankiweb printing press CLI to:

1) provide a central spot to translate and CATCH your new learnings.  Use Google Sheets' ability to call translation in the moment and persist those (unlike most translation tools)

2) automatically RELEASE those newly discovered words and phrases into the Anki system.  This gets the learner on a track to leverage Anki's concept of spaced repitition and their algotythm to practice new vocabulary/phrases right before you forget it again.


### 📚 Vocabulary → Anki Flashcards
[`workflows/sync_vocab_to_anki.md`](workflows/sync_vocab_to_anki.md)

Reads vocabulary from a two-tab Google Sheet and creates bidirectional Anki flashcards — works for any language pair (Spanish, French, Japanese, etc.).

**How it works:**
- Reads two sheet tabs: one with target-language words in column A, one with native-language words in column A
- Checks each entry against your existing Anki deck to skip duplicates
- Creates "Basic (and reversed card)" notes — 2 Anki cards per entry (word → translation and translation → word)
- Logs every run to `.tmp/` with counts of added, skipped, and errored entries

**Quick start:**
```bash
# 1. One-time setup: find your Anki deck ID and notetype ID
python tools/anki_setup.py

# 2. Preview without making changes
python tools/sync_vocab_to_anki.py --dry-run

# 3. Sync new words to Anki
python tools/sync_vocab_to_anki.py
```

---

## Setup

### Prerequisites
- Python 3.8+
- [ankiweb-pp-cli](https://github.com/steipete/ankiweb-pp-cli) binary (for Anki)
- A Google Cloud project with the Sheets API enabled and OAuth credentials

### Install dependencies
```bash
pip install -r requirements.txt
```

### Configure environment
```bash
cp .env.example .env
```

Open `.env` and fill in the values. The `.env.example` file has detailed instructions for each variable, including how to find your Anki deck ID and notetype ID.

**Required variables for the vocab sync:**

| Variable | Description |
|----------|-------------|
| `GOOGLE_SHEET_ID` | ID from your sheet URL: `.../spreadsheets/d/<ID>/edit` |
| `TARGET_LANG_SHEET` | Tab name where col A = word in the language you're learning |
| `NATIVE_LANG_SHEET` | Tab name where col A = your native language word |
| `LEARNING_LANGUAGE` | Display name for logs (e.g. `Spanish`) |
| `ANKI_DECK_ID` | Numeric deck ID — run `python tools/anki_setup.py` to find it |
| `ANKI_NOTETYPE_ID` | Notetype ID for "Basic (and reversed card)" — same setup helper |
| `ANKIWEB_CLI_PATH` | Full path to the `ankiweb-pp-cli` binary on your machine |

### Google authentication
Place your `credentials.json` (downloaded from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)) in the project root. On the first run, a browser tab opens for authorization and `token.json` is saved automatically. Both files are gitignored.

---

## Project structure

```
tools/                  Python scripts — deterministic execution
  sync_vocab_to_anki.py   Main sync script
  anki_setup.py           One-time setup helper for Anki IDs

workflows/              Markdown SOPs — what to do and how
  sync_vocab_to_anki.md   Vocab sync workflow with setup steps and edge cases
  _TEMPLATE.md            Template for new workflows

.tmp/                   Intermediate files — regenerated each run, gitignored
.env                    Your credentials and config — gitignored
.env.example            Template with instructions for every variable
requirements.txt        Python dependencies
```

---

