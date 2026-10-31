#!/bin/sh
# Copies the merged image (bootloader 0x0, partitions 0x8000, boot_app0 0xe000,
# app 0x10000) that PlatformIO's esptool step already builds, to dist/ for web flashing.
# Usage: pio run -e firebeetle2_esp32s3 && tools/merge_bin.sh
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$here/dist"
cp "$here/.pio/build/firebeetle2_esp32s3/firmware.factory.bin" "$here/dist/kiro-crew-deck-firebeetle2.bin"
ls -l "$here/dist/kiro-crew-deck-firebeetle2.bin"
