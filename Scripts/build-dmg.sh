#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
# 2026-11-09: 脚本已移入 Scripts/，回退一层到项目根
SCRIPT_DIR="${SCRIPT_DIR:h}"
PLIST="$SCRIPT_DIR/Packaging/Info.plist"
VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$PLIST")
STAGING="$SCRIPT_DIR/dist/dmg-root"
FINAL_DMG="$SCRIPT_DIR/dist/vRemoter-$VERSION.dmg"

"$SCRIPT_DIR/Scripts/package-app.sh"

rm -rf "$STAGING" "$FINAL_DMG"
mkdir -p "$STAGING"
ditto "$SCRIPT_DIR/dist/build/vRemote.app" "$STAGING/vRemote.app"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "vRemoter $VERSION" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$FINAL_DMG"

rm -rf "$STAGING"
print "Built app-only update: $FINAL_DMG"
