# Workflow: [Name]

> One-sentence description of what this workflow accomplishes.

---

## Objective

[What does a successful run of this workflow look like? What is the end state?]

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Example: spreadsheet URL | User provides | Must be a Google Sheets URL |
| Example: date range | User provides | Format: YYYY-MM-DD |

## Tools Used

| Tool | Purpose |
|------|---------|
| `tools/example.py` | [What this script does] |

## Steps

1. **Gather inputs** — Ask the user for anything listed above that isn't already known.
2. **Run tool** — `python tools/example.py --arg value`
3. **Validate output** — Check `.tmp/output.csv` for expected structure.
4. **Deliver result** — [Describe where the final output lives: Sheet URL, email sent, etc.]

## Edge Cases & Known Quirks

- [Rate limits, API timeouts, auth failures — document anything that bit you here]

## Output

- **Intermediate:** `.tmp/` — disposable, regenerated each run
- **Final:** [Cloud destination, e.g. Google Sheet URL or Gmail draft]

---

*Last updated: [date] — [what changed]*
