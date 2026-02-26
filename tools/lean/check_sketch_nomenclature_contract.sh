#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

python3 - <<'PY'
import json
import pathlib
import re
import sys

root = pathlib.Path("app/bridge/firmware_templates")
if not root.exists():
    print("[check_sketch_nomenclature_contract] missing firmware_templates root")
    sys.exit(1)

errors: list[str] = []
checked = 0

for d in sorted(p for p in root.iterdir() if p.is_dir()):
    release_path = d / "release.json"
    if not release_path.exists():
        continue
    checked += 1
    name = d.name

    ino_files = sorted(d.glob("*.ino"))
    if len(ino_files) != 1:
        errors.append(f"{name}: expected exactly 1 .ino file, found {len(ino_files)}")
        continue
    ino_stem = ino_files[0].stem
    if ino_stem != name:
        errors.append(
            f"{name}: .ino stem mismatch (expected '{name}', found '{ino_stem}')"
        )

    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{name}: invalid release.json ({exc})")
        continue

    runtime_version = str(release.get("runtime_version", "")).strip()
    tune_version = str(release.get("tune_version", "")).strip()
    if not runtime_version:
        errors.append(f"{name}: release.json missing runtime_version")
    if not tune_version:
        errors.append(f"{name}: release.json missing tune_version")
    if runtime_version and not runtime_version.startswith(name + "."):
        errors.append(
            f"{name}: runtime_version must start with '{name}.' (found '{runtime_version}')"
        )

    header_path = d / "release_version.h"
    if not header_path.exists():
        errors.append(f"{name}: missing release_version.h")
    else:
        hdr = header_path.read_text(encoding="utf-8", errors="replace")
        m_runtime = re.search(
            r'#define\s+UPRIGHT_RUNTIME_VERSION\s+"([^"]+)"', hdr
        )
        m_tune = re.search(r'#define\s+UPRIGHT_TUNE_VERSION\s+"([^"]+)"', hdr)
        if not m_runtime:
            errors.append(f"{name}: release_version.h missing UPRIGHT_RUNTIME_VERSION")
        elif runtime_version and m_runtime.group(1) != runtime_version:
            errors.append(
                f"{name}: release_version.h runtime mismatch ('{m_runtime.group(1)}' != '{runtime_version}')"
            )
        if not m_tune:
            errors.append(f"{name}: release_version.h missing UPRIGHT_TUNE_VERSION")
        elif tune_version and m_tune.group(1) != tune_version:
            errors.append(
                f"{name}: release_version.h tune mismatch ('{m_tune.group(1)}' != '{tune_version}')"
            )

    manifest_path = d / "runtime_manifest_v1.json"
    if not manifest_path.exists():
        errors.append(f"{name}: missing runtime_manifest_v1.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{name}: invalid runtime_manifest_v1.json ({exc})")
            continue
        rel = manifest.get("release", {})
        if not isinstance(rel, dict):
            errors.append(f"{name}: manifest release node invalid")
        else:
            m_runtime = str(rel.get("runtime_version", "")).strip()
            m_tune = str(rel.get("tune_version", "")).strip()
            if runtime_version and m_runtime != runtime_version:
                errors.append(
                    f"{name}: manifest runtime mismatch ('{m_runtime}' != '{runtime_version}')"
                )
            if tune_version and m_tune != tune_version:
                errors.append(
                    f"{name}: manifest tune mismatch ('{m_tune}' != '{tune_version}')"
                )
        generated_by = str(manifest.get("generated_by", "")).strip()
        if generated_by != name:
            errors.append(
                f"{name}: manifest generated_by mismatch ('{generated_by}' != '{name}')"
            )

if errors:
    print("[check_sketch_nomenclature_contract] FAIL")
    for e in errors:
        print(f"- {e}")
    sys.exit(1)

print(f"[check_sketch_nomenclature_contract] PASS ({checked} templates checked)")
PY

