#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSET_ROOT="${ROOT_DIR}/app/ui/ops-console/public/board-assets"

mkdir -p "${ASSET_ROOT}"

download() {
  local url="$1"
  local out="$2"
  if [[ -z "${url}" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "${out}")"
  echo "sync: ${url} -> ${out}"
  if ! curl -L --fail --retry 2 --connect-timeout 10 --max-time 120 -o "${out}" "${url}"; then
    echo "warn: failed to mirror ${url}"
    rm -f "${out}"
  fi
}

sync_board() {
  local id="$1"
  local docs="$2"
  local pinout="$3"
  local schematic="$4"
  local cad="$5"
  local target="${ASSET_ROOT}/${id}"

  mkdir -p "${target}"
  download "${docs}" "${target}/docs.html"
  download "${pinout}" "${target}/pinout.pdf"
  download "${schematic}" "${target}/schematic.pdf"
  download "${cad}" "${target}/cad.zip"
}

sync_board "nano" \
  "https://docs.arduino.cc/hardware/nano/" \
  "https://docs.arduino.cc/resources/pinouts/A000005-full-pinout.pdf" \
  "https://docs.arduino.cc/resources/schematics/A000005-schematics.pdf" \
  "https://docs.arduino.cc/resources/cad/A000005-cad-files.zip"

sync_board "nano_every" \
  "https://docs.arduino.cc/hardware/nano-every/" \
  "https://docs.arduino.cc/resources/pinouts/ABX00028-full-pinout.pdf" \
  "https://docs.arduino.cc/resources/schematics/ABX00028-schematics.pdf" \
  "https://docs.arduino.cc/resources/cad/ABX00028-cad-files.zip"

sync_board "nano_esp32" \
  "https://docs.arduino.cc/hardware/nano-esp32/" \
  "https://docs.arduino.cc/resources/pinouts/ABX00083-full-pinout.pdf" \
  "https://docs.arduino.cc/resources/schematics/ABX00083-schematics.pdf" \
  "https://docs.arduino.cc/resources/cad/ABX00083-cad-files.zip"

sync_board "uno" \
  "https://docs.arduino.cc/hardware/uno-rev3/" \
  "https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf" \
  "https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf" \
  "https://docs.arduino.cc/resources/cad/A000066-cad-files.zip"

sync_board "esp32_devkitc_v4" \
  "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html" \
  "" \
  "https://dl.espressif.com/dl/schematics/esp32_devkitc_v4-sch.pdf" \
  ""

sync_board "esp32_s3_devkitc_1" \
  "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide.html" \
  "" \
  "https://dl.espressif.com/dl/schematics/esp32-s3-devkitc-1-v1.0-sch.pdf" \
  ""

mkdir -p "${ASSET_ROOT}/teensy40" "${ASSET_ROOT}/teensy41"
download "https://www.pjrc.com/store/teensy40.html" "${ASSET_ROOT}/teensy40/docs.html"
download "https://www.pjrc.com/teensy/pinout.html" "${ASSET_ROOT}/teensy40/pinout.html"
download "https://www.pjrc.com/store/teensy41.html" "${ASSET_ROOT}/teensy41/docs.html"
download "https://www.pjrc.com/teensy/pinout.html" "${ASSET_ROOT}/teensy41/pinout.html"

echo "board asset sync complete: ${ASSET_ROOT}"
