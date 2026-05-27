# CatchAndRelease

WAT framework workflows for language learning automation.

Reads vocabulary rows from a Google Sheet and creates Anki flashcards automatically.
Marks each row ✓ when done — re-runs are always safe.

---

## Quick Start

**New here? Run the setup wizard** (handles everything, ~5–10 minutes):
```
python tools/setup.py
```

**Already set up? Sync new vocab cards:**
```
python tools/sheets_to_anki.py --dry-run   # preview what will be added
python tools/sheets_to_anki.py             # create the cards
```

---

## How it works

1. You keep vocabulary in a Google Sheet (front in column A, translation in column B)
2. Run `sheets_to_anki.py` — it creates a `Basic (and reversed card)` note in Anki for each unchecked row
3. A ✓ is written to column D so the row is skipped on future runs

---

## Docs

| Document | What it covers |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Architecture — how the WAT framework works |
| [workflows/sheets_to_anki.md](workflows/sheets_to_anki.md) | Full setup guide, troubleshooting, cookie refresh |
| [tools/README.md](tools/README.md) | All available scripts |
| [.env.example](.env.example) | Every configurable setting with descriptions |
