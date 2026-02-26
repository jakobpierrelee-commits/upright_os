#!/usr/bin/env python3
"""Validate dependency matrix artifact shape for architecture boundary enforcement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[check_dependency_matrix] missing file: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[check_dependency_matrix] invalid JSON at {path}: {exc}")


def _validate_matrix(matrix: Any) -> tuple[int, int]:
    if not isinstance(matrix, dict):
        raise SystemExit("[check_dependency_matrix] matrix root must be an object")

    version = matrix.get("version")
    if not isinstance(version, (str, int)):
        raise SystemExit("[check_dependency_matrix] `version` must be string or number")

    zones = matrix.get("zones")
    if not isinstance(zones, dict) or not zones:
        raise SystemExit("[check_dependency_matrix] `zones` must be a non-empty object")

    normalized_zones: dict[str, list[str]] = {}
    for zone, prefixes in zones.items():
        if not isinstance(zone, str) or not zone.strip():
            raise SystemExit("[check_dependency_matrix] zone name must be non-empty string")
        if not isinstance(prefixes, list) or not prefixes:
            raise SystemExit(
                f"[check_dependency_matrix] zone `{zone}` must map to a non-empty list"
            )
        clean_prefixes: list[str] = []
        for prefix in prefixes:
            if not isinstance(prefix, str) or not prefix.strip():
                raise SystemExit(
                    f"[check_dependency_matrix] zone `{zone}` contains invalid prefix"
                )
            clean_prefixes.append(prefix.strip().rstrip("/"))
        normalized_zones[zone] = clean_prefixes

    edges = matrix.get("allowed_import_edges")
    if not isinstance(edges, list) or not edges:
        raise SystemExit(
            "[check_dependency_matrix] `allowed_import_edges` must be a non-empty list"
        )

    edge_count = 0
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise SystemExit(
                "[check_dependency_matrix] every edge must be a 2-item list [from, to]"
            )
        src, dst = edge
        if src not in normalized_zones or dst not in normalized_zones:
            raise SystemExit(
                "[check_dependency_matrix] edge references unknown zone "
                f"({src!r} -> {dst!r})"
            )
        edge_count += 1

    return len(normalized_zones), edge_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, help="Path to dependency matrix JSON")
    parser.add_argument("--schema", required=True, help="Path to schema JSON")
    args = parser.parse_args()

    matrix_path = Path(args.matrix)
    schema_path = Path(args.schema)

    matrix_json = _load_json(matrix_path)
    schema_json = _load_json(schema_path)
    if not isinstance(schema_json, dict):
        raise SystemExit("[check_dependency_matrix] schema root must be an object")

    zone_count, edge_count = _validate_matrix(matrix_json)
    print(
        "[check_dependency_matrix] PASS "
        f"(zones={zone_count}, allowed_edges={edge_count}, matrix={matrix_path})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
