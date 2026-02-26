#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

usage() {
  cat <<'EOF'
Usage:
  tools/lean/new_sketch_version.sh --from <src_folder> --to <dst_folder> [--runtime-version <ver>] [--tune-version <ver>]

Examples:
  tools/lean/new_sketch_version.sh \
    --from app/bridge/firmware_templates/profiled_runtime_v1 \
    --to app/bridge/firmware_templates/profiled_runtime_v1_3_observability \
    --runtime-version profiled_runtime_v1.3.0 \
    --tune-version tune_v1
EOF
}

SRC=""
DST=""
RUNTIME_VER=""
TUNE_VER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      SRC="${2:-}"
      shift 2
      ;;
    --to)
      DST="${2:-}"
      shift 2
      ;;
    --runtime-version)
      RUNTIME_VER="${2:-}"
      shift 2
      ;;
    --tune-version)
      TUNE_VER="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[new_sketch_version] unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${SRC}" || -z "${DST}" ]]; then
  echo "[new_sketch_version] --from and --to are required" >&2
  usage
  exit 2
fi

if [[ ! -d "${SRC}" ]]; then
  echo "[new_sketch_version] source folder not found: ${SRC}" >&2
  exit 1
fi

if [[ -e "${DST}" ]]; then
  echo "[new_sketch_version] destination already exists: ${DST}" >&2
  exit 1
fi

echo "[new_sketch_version] cloning ${SRC} -> ${DST}"
cp -R "${SRC}" "${DST}"

RELEASE_JSON="${DST}/release.json"
if [[ ! -f "${RELEASE_JSON}" ]]; then
  echo "[new_sketch_version] missing release.json in destination: ${RELEASE_JSON}" >&2
  exit 1
fi

if [[ -n "${RUNTIME_VER}" ]]; then
  tmp="$(mktemp)"
  jq --arg v "${RUNTIME_VER}" '.runtime_version=$v' "${RELEASE_JSON}" > "${tmp}"
  mv "${tmp}" "${RELEASE_JSON}"
fi

if [[ -n "${TUNE_VER}" ]]; then
  tmp="$(mktemp)"
  jq --arg v "${TUNE_VER}" '.tune_version=$v' "${RELEASE_JSON}" > "${tmp}"
  mv "${tmp}" "${RELEASE_JSON}"
fi

python3 tools/lean/sync_release_metadata.py --template-dir "${DST}"

echo "[new_sketch_version] created: ${DST}"
echo "[new_sketch_version] release:"
cat "${RELEASE_JSON}" | jq .

