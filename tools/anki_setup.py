#!/usr/bin/env python3
"""
anki_setup.py

One-time setup helper for the Anki vocabulary sync workflow.

Connects to AnkiWeb via the ankiweb-pp-cli binary, lists your decks and
available notetypes with their numeric IDs, then lets you pick which ones
to use. Offers to write the selected IDs directly into your .env file.

Usage:
    python tools/anki_setup.py
    python tools/anki_setup.py --cli-path "C:\\path\\to\\ankiweb-pp-cli.exe"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list) -> tuple:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", str(exc)


def bail(msg: str):
    print(f"\n✗  {msg}", file=sys.stderr)
    sys.exit(1)


def hr(char="─", width=60):
    print(char * width)


def pick(prompt: str, options: list) -> int:
    """
    Display a numbered list and return the 0-based index the user selects.
    options is a list of display strings.
    """
    for i, label in enumerate(options, 1):
        print(f"  {i:>3}.  {label}")
    print()
    while True:
        raw = input(f"{prompt} (1–{len(options)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"       Please enter a number between 1 and {len(options)}.")


def write_env_value(key: str, value: str, env_path: Path):
    """
    Update or append a KEY=value line in the .env file.
    Preserves all other content and comments.
    """
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    # Match lines like:  KEY=   or  KEY=oldvalue   (with optional inline comment)
    pattern = re.compile(
        rf"^({re.escape(key)}\s*=)[^\n]*$", re.MULTILINE
    )

    new_line = f"{key}={value}"
    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        # Key not present — append it
        content = content.rstrip("\n") + f"\n{new_line}\n"

    env_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Interactive setup helper: find your Anki deck ID and notetype ID.",
    )
    parser.add_argument(
        "--cli-path",
        help="Full path to the ankiweb-pp-cli binary (overrides ANKIWEB_CLI_PATH in .env).",
    )
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         AnkiWeb Vocab Sync — Setup Helper                ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # ------------------------------------------------------------------
    # 1. Find the CLI binary
    # ------------------------------------------------------------------
    cli = args.cli_path or os.getenv("ANKIWEB_CLI_PATH", "")

    if not cli:
        print("ANKIWEB_CLI_PATH is not set in your .env and --cli-path was not provided.")
        print()
        print("Common locations:")
        print("  Windows: C:\\Users\\<you>\\printing-press\\library\\ankiweb-pp-cli\\ankiweb-pp-cli.exe")
        print("  Mac/Linux: ~/printing-press/library/ankiweb-pp-cli/ankiweb-pp-cli")
        print()
        cli = input("Enter the full path to ankiweb-pp-cli: ").strip().strip('"').strip("'")
        if not cli:
            bail("No path provided. Exiting.")

    cli_path = Path(cli)
    if not cli_path.exists():
        bail(
            f"Binary not found at: {cli}\n"
            "  Check ANKIWEB_CLI_PATH in your .env, or pass --cli-path."
        )

    print(f"✓  Binary found: {cli_path}")

    # ------------------------------------------------------------------
    # 2. Check auth / connectivity
    # ------------------------------------------------------------------
    print("   Checking AnkiWeb session...")
    code, out, err = run([str(cli_path), "account", "status"])
    if code != 0:
        print()
        print("✗  Not authenticated with AnkiWeb.")
        print("   Run this to log in, then re-run this script:")
        print(f"     {cli_path} account login --username you@example.com")
        sys.exit(1)
    print("✓  Authenticated with AnkiWeb.")
    print()

    # ------------------------------------------------------------------
    # 3. Fetch decks
    # ------------------------------------------------------------------
    hr()
    print("STEP 1 OF 2 — Choose your vocabulary deck")
    hr()
    print()

    code, out, err = run([str(cli_path), "decks", "list", "--json"])
    if code != 0:
        bail(f"Could not fetch decks: {err or out}")

    try:
        decks = json.loads(out)
    except json.JSONDecodeError:
        bail(f"Unexpected output from decks list:\n{out[:300]}")

    if not decks:
        bail("No decks found in your AnkiWeb account.")

    # Build display labels
    deck_labels = []
    for d in decks:
        name = d.get("name") or d.get("field_2", "?")
        did  = d.get("deck_id") or d.get("field_1", "?")
        new  = d.get("new_count", "")
        rev  = d.get("review_count", "")
        info = f"  [{new} new, {rev} review]" if new != "" else ""
        deck_labels.append(f"{name}{info}  (id: {did})")

    chosen_deck_idx = pick("Which deck should new vocab cards go into?", deck_labels)
    chosen_deck = decks[chosen_deck_idx]
    deck_id  = str(chosen_deck.get("deck_id") or chosen_deck.get("field_1"))
    deck_name = chosen_deck.get("name") or chosen_deck.get("field_2", "?")
    print(f"\n✓  Selected deck: {deck_name}  (id: {deck_id})")
    print()

    # ------------------------------------------------------------------
    # 4. Fetch notetypes
    # ------------------------------------------------------------------
    hr()
    print("STEP 2 OF 2 — Choose a notetype (card template)")
    hr()
    print()
    print("For bidirectional vocab cards (recommended), choose:")
    print('  "Basic (and reversed card)" — creates 2 cards per entry')
    print('    Card 1: target language → native language')
    print('    Card 2: native language → target language')
    print()

    code, out, err = run([str(cli_path), "notes", "editor-info", "--json"])
    if code != 0:
        bail(f"Could not fetch notetypes: {err or out}")

    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        bail(f"Unexpected output from notes editor-info:\n{out[:300]}")

    # editor-info returns {"field_1": [...notetypes...], "field_2": [...decks...], ...}
    # Notetypes are in field_1 with sub-keys field_1=id, field_2=name
    if isinstance(raw, dict) and "field_1" in raw:
        notetypes_raw = raw["field_1"]
    elif isinstance(raw, list):
        notetypes_raw = raw
    else:
        bail(f"Unexpected notetype format:\n{str(raw)[:300]}")

    notetypes = []
    for nt in notetypes_raw:
        nid  = nt.get("id") or nt.get("field_1")
        name = nt.get("name") or nt.get("field_2", "?")
        notetypes.append({"id": nid, "name": name})

    if not notetypes:
        bail("No notetypes found.")

    # Pre-select "Basic (and reversed card)" as default if present
    default_idx = next(
        (i for i, n in enumerate(notetypes) if "reversed" in n["name"].lower()),
        0,
    )

    nt_labels = [
        f"{n['name']}  (id: {n['id']})"
        + ("  ← recommended for vocab" if "reversed" in n["name"].lower() else "")
        for n in notetypes
    ]

    print(f"(Default suggestion is option {default_idx + 1})\n")
    chosen_nt_idx = pick("Which notetype should vocab notes use?", nt_labels)
    chosen_nt = notetypes[chosen_nt_idx]
    nt_id   = str(chosen_nt["id"])
    nt_name = chosen_nt["name"]
    print(f"\n✓  Selected notetype: {nt_name}  (id: {nt_id})")
    print()

    # ------------------------------------------------------------------
    # 5. Summary + write to .env
    # ------------------------------------------------------------------
    hr("═")
    print("Summary")
    hr("═")
    print(f"  ANKI_DECK_ID      = {deck_id}   ({deck_name})")
    print(f"  ANKI_NOTETYPE_ID  = {nt_id}   ({nt_name})")
    print(f"  ANKIWEB_CLI_PATH  = {cli}")
    hr("═")
    print()

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        answer = input("Write these values to your .env file? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            write_env_value("ANKI_DECK_ID",     deck_id,  env_path)
            write_env_value("ANKI_NOTETYPE_ID", nt_id,    env_path)
            write_env_value("ANKIWEB_CLI_PATH", str(cli_path), env_path)
            print(f"\n✓  .env updated: {env_path}")
        else:
            print("\nNo changes made. Copy the values above into your .env manually.")
    else:
        print(f"No .env file found at {env_path}.")
        print("Copy .env.example to .env, then add the values above.")

    print()
    print("All done! Next steps:")
    print("  1. Set GOOGLE_SHEET_ID, TARGET_LANG_SHEET, NATIVE_LANG_SHEET in .env")
    print("  2. python tools/sync_vocab_to_anki.py --dry-run")
    print("  3. python tools/sync_vocab_to_anki.py")
    print()


if __name__ == "__main__":
    main()
