#!/usr/bin/env bash
# Run an original Fast4DReg macro in a real ImageJ 1.x GUI on a virtual display.
# Usage: run_fiji_macro.sh IMAGEJ_DIR MACRO.ijm SETTINGS.json WORKDIR [TIMEOUT_S]
set -euo pipefail
IJ_DIR=$1; MACRO=$2; SETTINGS=$3; WORK=$4; TIMEOUT=${5:-3600}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK"
python3 "$HERE/patch_macro.py" "$MACRO" "$SETTINGS" "$WORK/patched.ijm"
LOG="$WORK/fiji_log.txt"; rm -f "$LOG"
xvfb-run -a java -Xmx${FIJI_XMX:-8g} -Dplugins.dir="$IJ_DIR/plugins" -cp "$IJ_DIR/ij.jar" \
  ij.ImageJ -ijpath "$IJ_DIR" -macro "$WORK/patched.ijm" "$LOG" > "$WORK/java_stdout.txt" 2>&1 &
PID=$!
for ((i = 0; i < TIMEOUT; i++)); do
  if [[ -s "$LOG" ]]; then break; fi
  if ! kill -0 "$PID" 2>/dev/null; then echo "ImageJ exited before finishing" >&2; exit 1; fi
  sleep 1
done
pkill -P "$PID" 2>/dev/null || true; kill "$PID" 2>/dev/null || true
for p in $(pgrep -x java); do kill "$p" 2>/dev/null || true; done
if ! grep -q F4DR_HEADLESS_DONE "$LOG" 2>/dev/null; then echo "Fiji macro timed out" >&2; exit 1; fi
cat "$LOG"
