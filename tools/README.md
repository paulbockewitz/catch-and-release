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
| *(add entries as scripts are created)* | |
