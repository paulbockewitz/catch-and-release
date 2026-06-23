# Vocabulary Workflow

```mermaid
flowchart TD
    USER["👤 User types Spanish or English\nword/phrase in Google Sheets\n(Column A)"]

    subgraph SHEET["📊 Google Sheet — 'Translate' tab"]
        direction LR
        COL_A["Col A\nSpanish input"]
        COL_B["Col B\nEnglish translation"]
        COL_C["Col C\nDetected language\n(es / en)"]
        COL_E["Col E\nDreaming URL\n(clickable HYPERLINK)"]
        COL_F["Col F\nVideo timestamp"]
    end

    subgraph SPELLCHECK["⚡ Real-time: vocab_spell_check.gs (onEdit trigger)"]
        DIACRITICS{"Spanish\ndiacritics?"}
        LT_ES["LanguageTool\nlanguage=es"]
        LT_EN["LanguageTool\nlanguage=en-US"]
        ORACLE["detectLanguage()\nzero-match oracle"]
        WRITE_C["Write 'es'/'en'\n→ Col C"]
        WRITE_B["Write GOOGLETRANSLATE\nformula → Col B\n(if empty)"]
        CORRECT["Apply correction\nin-place\n(save original as note)"]

        DIACRITICS -->|"yes (es only)"| LT_ES
        DIACRITICS -->|no| LT_ES
        DIACRITICS -->|no| LT_EN
        LT_ES --> ORACLE
        LT_EN --> ORACLE
        ORACLE --> WRITE_C
        WRITE_C --> WRITE_B
        WRITE_B --> CORRECT
    end

    subgraph ENRICH["🎬 enrich_dreaming_urls.py (manual / scheduled)"]
        ROUTE{"Lang col\n= 'es'?"}
        QUERY_A["dreaming-pp-cli concordance\n(query Col A — Spanish)"]
        QUERY_B["dreaming-pp-cli concordance\n(query Col B — Spanish)"]
        HYPERLINK["Write =HYPERLINK formula\n→ Col E\nWrite timestamp\n→ Col F"]
        NO_MATCH["Write 'no matches'\n→ Col E\n(skip on future runs)"]

        ROUTE -->|yes| QUERY_A
        ROUTE -->|no| QUERY_B
        QUERY_A -->|hit| HYPERLINK
        QUERY_B -->|hit| HYPERLINK
        QUERY_A -->|no hit| NO_MATCH
        QUERY_B -->|no hit| NO_MATCH
    end

    subgraph ANKI["🃏 sheets_to_anki.py (manual / scheduled)"]
        READ["Read all rows\n(skip already-synced)"]
        NOTE["Create Anki note\nFront: Spanish\nBack: English"]
        SYNC["Sync to AnkiWeb\nvia ankiweb-pp-cli"]

        READ --> NOTE --> SYNC
    end

    USER --> SHEET
    SHEET --> SPELLCHECK
    SPELLCHECK -->|"corrects Col A"| SHEET

    SHEET --> ENRICH
    ENRICH -->|"writes Col E, F"| SHEET

    SHEET --> ANKI

    ANKI --> ANKIWEB["📱 AnkiWeb\n(available on all devices)"]
    COL_E -->|"user clicks link"| DREAMING["🎥 Dreaming.com\nvideo at exact timestamp"]
```

## Column map

| Col | Content | Written by |
|-----|---------|-----------|
| A | Spanish or English word / phrase (input side) | User |
| B | Translation into the other language | GOOGLETRANSLATE formula (GAS-written on first edit) |
| C | Detected language (`es` / `en`) | `vocab_spell_check.gs` |
| E | Dreaming.com video URL (clickable HYPERLINK formula) | `enrich_dreaming_urls.py` |
| F | Video timestamp for the first concordance hit | `enrich_dreaming_urls.py` |

## Language routing in enrichment

- **Col C = `es`** → the Spanish word is in Col A → query Col A  
- **Col C = `en`** → the Spanish translation is in Col B → query Col B  
- **Col C blank** → falls back to Col B

## Tools

| Tool | Trigger | What it does |
|------|---------|-------------|
| `vocab_spell_check.gs` | Every Col A edit (Apps Script onEdit) | Detects language (writes Col C), writes GOOGLETRANSLATE formula to Col B, corrects spelling/accents, saves original as cell note |
| `enrich_dreaming_urls.py` | Manual or scheduled | Queries dreaming-pp-cli concordance, writes HYPERLINK + timestamp, batches all writes in one API call |
| `sheets_to_anki.py` | Manual or scheduled | Reads sheet, creates Anki notes, syncs to AnkiWeb via ankiweb-pp-cli |
