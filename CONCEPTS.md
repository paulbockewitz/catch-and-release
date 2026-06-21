# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary from the vocab-workflow area, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Vocab Workflow

### Dreaming URL
A URL pointing to a Dreaming Spanish video at the exact timestamp where a Spanish word or phrase appears in native speech. Stored in column E of the Vocab Sheet as a clickable hyperlink formula. Produced by the enrichment process.

### Enrichment
The automated process of finding a Dreaming URL for each Spanish vocabulary word in the Vocab Sheet and writing it to the URL column. A row is considered enriched once it has any value in the URL column; rows with no matches are marked "no matches" so they are not re-queried on future runs.

### Vocab Sheet
The Google Sheet that serves as the central vocabulary log for this project. Each row is one Spanish word or phrase, with columns for the Spanish input, English translation, detected language, Dreaming URL, and video timestamp. The spreadsheet is the source of truth; flashcards, Dreaming links, and auto-corrections all derive from it.
