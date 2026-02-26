#!/usr/bin/env python3
"""
Extract a class from server.py by removing it entirely.

Usage:
    python3 tools/extract_class.py <class_name> [--dry-run]

Example:
    python3 tools/extract_class.py AIManager --dry-run
    python3 tools/extract_class.py AIManager
"""

import argparse
import re
import sys
from pathlib import Path


def find_class_boundaries(content: str, class_name: str) -> tuple[int, int] | None:
    """Find the start and end line indices (0-indexed) of a class definition."""
    lines = content.split("\n")

    # Find class start
    class_pattern = re.compile(rf"^class {class_name}\s*[:\(]")
    start_idx = None

    for i, line in enumerate(lines):
        if class_pattern.match(line):
            start_idx = i
            break

    if start_idx is None:
        return None

    # Find class end by tracking indentation
    # Class ends when we hit a line with no indentation (and non-empty, non-comment)
    end_idx = start_idx + 1

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            end_idx = i + 1
            continue

        # Skip comments at any indentation
        if stripped.startswith("#"):
            end_idx = i + 1
            continue

        # If line starts with non-whitespace, class is over
        if line and not line[0].isspace():
            break

        end_idx = i + 1

    return (start_idx, end_idx)


def remove_class(content: str, class_name: str, comment: str = "") -> tuple[str, int]:
    """Remove a class from content and return (new_content, lines_removed)."""
    boundaries = find_class_boundaries(content, class_name)

    if boundaries is None:
        raise ValueError(f"Class '{class_name}' not found")

    start_idx, end_idx = boundaries
    lines = content.split("\n")
    lines_removed = end_idx - start_idx

    # Build replacement (just a comment)
    replacement = [f"# {class_name} moved to domain module"]
    if comment:
        replacement.append(f"# {comment}")

    new_lines = lines[:start_idx] + replacement + lines[end_idx:]

    return "\n".join(new_lines), lines_removed


def main():
    parser = argparse.ArgumentParser(description="Extract a class from server.py")
    parser.add_argument("class_name", help="Name of the class to remove")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without modifying",
    )
    parser.add_argument(
        "--file",
        default="app/bridge/server.py",
        help="Target file (default: app/bridge/server.py)",
    )
    parser.add_argument("--comment", default="", help="Additional comment to add")

    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    target = repo_root / args.file

    if not target.exists():
        print(f"Error: {target} not found")
        return 1

    content = target.read_text(encoding="utf-8")
    original_lines = len(content.split("\n"))

    boundaries = find_class_boundaries(content, args.class_name)

    if boundaries is None:
        print(f"Error: Class '{args.class_name}' not found in {target}")
        return 1

    start_idx, end_idx = boundaries
    lines_to_remove = end_idx - start_idx

    print(f"Found class '{args.class_name}':")
    print(f"  Start line: {start_idx + 1}")
    print(f"  End line:   {end_idx}")
    print(f"  Lines:      {lines_to_remove}")

    if args.dry_run:
        print("\n[DRY RUN] Would remove these lines:")
        lines = content.split("\n")
        # Show first 5 and last 5 lines
        preview_lines = lines[start_idx : min(start_idx + 5, end_idx)]
        for i, line in enumerate(preview_lines):
            print(f"  {start_idx + i + 1}: {line[:80]}...")
        if lines_to_remove > 10:
            print(f"  ... ({lines_to_remove - 10} more lines) ...")
            for i, line in enumerate(lines[max(start_idx + 5, end_idx - 5) : end_idx]):
                actual_idx = max(start_idx + 5, end_idx - 5) + i
                print(f"  {actual_idx + 1}: {line[:80]}...")
        return 0

    new_content, removed = remove_class(content, args.class_name, args.comment)
    new_lines = len(new_content.split("\n"))

    target.write_text(new_content, encoding="utf-8")

    print(f"\n✅ Removed {removed} lines")
    print(f"   {original_lines} → {new_lines} lines")
    print(f"\nVerify with: python3 -m py_compile {args.file}")


if __name__ == "__main__":
    sys.exit(main() or 0)
