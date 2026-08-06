#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
APP="$SCRIPT_DIR/dist/vRemote.app"
CONTENTS="$APP/Contents"

cd "$SCRIPT_DIR"
swift build -c release

rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS"
cp "$SCRIPT_DIR/.build/release/vRemote" "$CONTENTS/MacOS/vRemote"
cp "$SCRIPT_DIR/Packaging/Info.plist" "$CONTENTS/Info.plist"
chmod 755 "$CONTENTS/MacOS/vRemote"

# Give the ad-hoc build a stable designated requirement. Without this,
# codesign falls back to a CDHash-only requirement, so every rebuild looks
# like a different application to Accessibility/Input Monitoring (TCC).
codesign \
  --force \
  --deep \
  --sign - \
  --timestamp=none \
  --requirements '=designated => identifier "local.simaqingfeng.vRemote"' \
  "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
print "Built: $APP"
