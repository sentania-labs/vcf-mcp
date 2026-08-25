#!/usr/bin/env python3
"""Generate the skills index from the skills directory tree.

Produces skills/index.json containing the catalog of all skills and their
digests, alongside a 'current' alias mapping.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# Add src to sys.path to import vcf_mcp
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from vcf_mcp.skills import build_index_data

SKILLS_DIR = Path(__file__).parent.parent / "skills"
INDEX_PATH = SKILLS_DIR / "index.json"

def generate_index() -> None:
    if not SKILLS_DIR.exists():
        print(f"Directory {SKILLS_DIR} not found.")
        return

    index_data = build_index_data(SKILLS_DIR)

    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, sort_keys=True)
        f.write("\n")

    catalog = index_data.get("skills", [])
    print(f"Generated index with {len(catalog)} skills.")

if __name__ == "__main__":
    generate_index()
