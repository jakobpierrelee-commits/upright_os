#!/usr/bin/env python3
"""Enforce import boundaries using docs/contracts/dependency matrix."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
_TS_IMPORT_RE = re.compile(
    r"(?:import|export)\\s+(?:type\\s+)?(?:[^;]*?)\\s+from\\s+[\"']([^\"']+)[\"']"
)
_TS_REQUIRE_RE = re.compile(r"require\\(\\s*[\"']([^\"']+)[\"']\\s*\\)")


def _load_matrix(path: Path) -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[check_import_boundaries] missing matrix: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[check_import_boundaries] invalid matrix JSON: {exc}")

    zones_raw = payload.get("zones")
    edges_raw = payload.get("allowed_import_edges")
    if not isinstance(zones_raw, dict) or not isinstance(edges_raw, list):
        raise SystemExit("[check_import_boundaries] matrix must define zones + allowed_import_edges")

    zones: dict[str, list[str]] = {}
    for zone, prefixes in zones_raw.items():
        if not isinstance(zone, str) or not isinstance(prefixes, list):
            raise SystemExit("[check_import_boundaries] invalid zone definition")
        zones[zone] = [p.strip().rstrip("/") for p in prefixes if isinstance(p, str) and p.strip()]

    allowed_edges: set[tuple[str, str]] = set()
    for edge in edges_raw:
        if isinstance(edge, list) and len(edge) == 2 and edge[0] in zones and edge[1] in zones:
            allowed_edges.add((edge[0], edge[1]))

    if not zones or not allowed_edges:
        raise SystemExit("[check_import_boundaries] zones and allowed edges must be non-empty")

    return zones, allowed_edges


def _zone_for_path(path: Path, repo_root: Path, zones: dict[str, list[str]]) -> str | None:
    rel = path.relative_to(repo_root).as_posix()
    best_zone: str | None = None
    best_len = -1
    for zone, prefixes in zones.items():
        for prefix in prefixes:
            if rel == prefix or rel.startswith(prefix + "/"):
                if len(prefix) > best_len:
                    best_zone = zone
                    best_len = len(prefix)
    return best_zone


def _resolve_relative_import(source_file: Path, import_spec: str) -> Path | None:
    base = source_file.parent
    target = (base / import_spec).resolve()
    candidates = [target]

    for ext in CODE_EXTS:
        candidates.append(Path(str(target) + ext))
    for ext in CODE_EXTS:
        candidates.append(target / ("index" + ext))

    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    return None


def _extract_import_targets(file_path: Path, repo_root: Path) -> list[Path]:
    targets: list[Path] = []
    text = file_path.read_text(encoding="utf-8", errors="replace")

    if file_path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return targets

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    dots = "." * node.level
                    suffix = node.module or ""
                    spec = dots + suffix
                    rel_spec = spec.replace(".", "/") if spec else ""
                    if rel_spec:
                        rel_spec = rel_spec.rstrip("/")
                    parent_walk = file_path.parent
                    for _ in range(node.level - 1):
                        parent_walk = parent_walk.parent
                    if node.module:
                        parent_walk = parent_walk / node.module.replace(".", "/")
                    if parent_walk.exists():
                        if parent_walk.is_dir():
                            init_py = parent_walk / "__init__.py"
                            if init_py.exists():
                                targets.append(init_py)
                        else:
                            targets.append(parent_walk)
                elif node.module and node.module.startswith("app."):
                    abs_path = repo_root / (node.module.replace(".", "/") + ".py")
                    if abs_path.exists():
                        targets.append(abs_path)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app."):
                        abs_path = repo_root / (alias.name.replace(".", "/") + ".py")
                        if abs_path.exists():
                            targets.append(abs_path)
        return targets

    specs: list[str] = []
    specs.extend(_TS_IMPORT_RE.findall(text))
    specs.extend(_TS_REQUIRE_RE.findall(text))
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        if spec.startswith("."):
            resolved = _resolve_relative_import(file_path, spec)
            if resolved:
                targets.append(resolved)
        elif spec.startswith("app/"):
            candidate = repo_root / spec
            if candidate.is_file():
                targets.append(candidate)
            else:
                resolved = _resolve_relative_import(repo_root / "_dummy.ts", "./" + spec)
                if resolved:
                    targets.append(resolved)

    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, help="Path to dependency matrix JSON")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    zones, allowed_edges = _load_matrix(Path(args.matrix))

    violations: list[str] = []
    scanned = 0
    boundary_scoped = 0

    app_root = repo_root / "app"
    if not app_root.exists():
        raise SystemExit(f"[check_import_boundaries] missing app root: {app_root}")

    for file_path in app_root.rglob("*"):
        if not file_path.is_file() or file_path.suffix not in CODE_EXTS:
            continue
        scanned += 1

        src_zone = _zone_for_path(file_path, repo_root, zones)
        if not src_zone:
            continue
        boundary_scoped += 1

        targets = _extract_import_targets(file_path, repo_root)
        for target in targets:
            if not target.exists():
                continue
            dst_zone = _zone_for_path(target.resolve(), repo_root, zones)
            if not dst_zone or dst_zone == src_zone:
                continue
            if (src_zone, dst_zone) not in allowed_edges:
                rel_src = file_path.resolve().relative_to(repo_root).as_posix()
                rel_dst = target.resolve().relative_to(repo_root).as_posix()
                violations.append(
                    f"{rel_src}: forbidden edge {src_zone} -> {dst_zone} via {rel_dst}"
                )

    if violations:
        print("[check_import_boundaries] FAIL")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(
        "[check_import_boundaries] PASS "
        f"(scanned={scanned}, boundary_scoped={boundary_scoped}, zones={len(zones)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
