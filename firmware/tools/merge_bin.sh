#!/bin/sh
# Copies the merged image (bootloader 0x0, partitions 0x8000, boot_app0 0xe000,
# app 0x10000) that PlatformIO's esptool step already builds, to dist/ for web flashing.
# Usage: pio run -e heltec_v4 && tools/merge_bin.sh [env] [output-name]
set -e
env=${1:-heltec_v4}
name=${2:-huddleboard-heltec-v4}
here=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$here/dist"
cp "$here/.pio/build/$env/firmware.factory.bin" "$here/dist/$name.bin"
ls -l "$here/dist/$name.bin"
