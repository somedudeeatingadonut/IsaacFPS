#!/usr/bin/env bash
# Build the IsaacFPS native layer.
#
# Requirements:
#   - zig (any recent version) on PATH, or: pip install ziglang
#     (zig bundles a complete mingw-w64 environment, so no separate
#      Windows toolchain is needed)
#
# Outputs land in native/dist/ :
#   isaacfps_native.dll   - the hook DLL
#   isaacfps_injector.exe - injects/ejects it into a running isaac-ng.exe
set -euo pipefail
cd "$(dirname "$0")"

if command -v zig >/dev/null 2>&1; then
    ZIGCC="zig cc"
elif command -v python3 >/dev/null 2>&1 && python3 -m ziglang version >/dev/null 2>&1; then
    ZIGCC="python3 -m ziglang cc"
else
    echo "zig not found. Install it, or: pip install ziglang" >&2
    exit 1
fi

TARGET="x86-windows-gnu" # isaac-ng.exe is a 32-bit process
OUT=dist
mkdir -p "$OUT"

echo "[1/3] host unit tests (sigscan / adaptive / budget / config)"
cc -O2 -Wall -Wextra -o /tmp/ifps_native_tests tests/test_native.c \
    src/sigscan.c src/adaptive.c src/budget.c src/config.c
/tmp/ifps_native_tests

echo "[2/3] isaacfps_native.dll (${TARGET})"
$ZIGCC -target "$TARGET" -O2 -shared -o "$OUT/isaacfps_native.dll" \
    src/dllmain.c src/hooks.c src/sigscan.c src/adaptive.c src/budget.c \
    src/config.c \
    third_party/minhook/src/hook.c third_party/minhook/src/buffer.c \
    third_party/minhook/src/trampoline.c third_party/minhook/src/hde/hde32.c \
    -Ithird_party/minhook/include -Isrc

echo "[3/3] isaacfps_injector.exe (${TARGET})"
$ZIGCC -target "$TARGET" -O2 -o "$OUT/isaacfps_injector.exe" src/injector.c

echo "built: $OUT/isaacfps_native.dll $OUT/isaacfps_injector.exe"
