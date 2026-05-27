# tools/

Python scripts that handle deterministic execution — API calls, data transforms, file operations.

## Conventions

- Every script runs standalone: `python tools/<name>.py [args]`
- Load credentials at the top via `python-dotenv`:
  ```python
  from dotenv import load_dotenv
  load_dotenv()
  ```
- Write intermediate output to `../.tmp/`
- Write final deliverables to cloud services (Google Sheets, Drive, etc.)
- Document all arguments with `argparse` so `--help` works

## Scripts

| Script | Purpose |
|--------|---------|
| `setup.py` | **Start here.** Onboarding wizard — installs deps, sets up Google credentials, creates a vocabulary sheet, configures AnkiWeb, and writes `.env`. Safe to re-run. |
| `sheets_to_anki.py` | Reads vocabulary rows from a Google Sheet and creates Anki flashcards via the CLI. Writes ✓ to the done column after each success. |
