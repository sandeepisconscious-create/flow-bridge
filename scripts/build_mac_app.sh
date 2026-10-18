#!/usr/bin/env bash
# ==============================================================================
# Build FlowBridge.app and FlowBridge-Installer.dmg
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
APP_NAME="FlowBridge.app"
APP_PATH="$DIST_DIR/$APP_NAME"
DMG_NAME="FlowBridge-Installer.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

echo "🔨 Building FlowBridge macOS Application bundle..."

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 1. Compile AppleScript launcher into a macOS Application bundle (.app)
# When launched, it installs the permanent user LaunchAgent and runs the sync engine.
APPLESCRIPT_SOURCE="
on run
    set appDir to (POSIX path of (path to me))
    set scriptDir to appDir & \"Contents/Resources/flow_bridge.py\"
    set pyBin to do shell script \"which python3 || echo /usr/bin/python3\"
    set userHome to (POSIX path of (path to home folder))
    set targetDir to userHome & \".flow-bridge\"
    set targetScript to targetDir & \"/flow_bridge.py\"
    
    -- Auto-install into ~/.flow-bridge so the DMG volume doesn't stay locked
    do shell script \"mkdir -p \" & quoted form of targetDir & \" && cp \" & quoted form of scriptDir & \" \" & quoted form of targetScript & \" && chmod +x \" & quoted form of targetScript
    
    -- Register LaunchAgent service to start on boot
    do shell script quoted form of pyBin & \" \" & quoted form of targetScript & \" --install-service\"
    
    display notification \"Flow Bridge is active! Voice dictation is now auto-synced to your clipboard.\" with title \"Flow Bridge\" subtitle \"Dictation Hub Active\"
end run
"

osacompile -e "$APPLESCRIPT_SOURCE" -o "$APP_PATH"

# 2. Bundle python sync engine inside the app's Resources directory
RESOURCES_DIR="$APP_PATH/Contents/Resources"
mkdir -p "$RESOURCES_DIR"
cp "$REPO_ROOT/flow_bridge.py" "$RESOURCES_DIR/flow_bridge.py"
chmod +x "$RESOURCES_DIR/flow_bridge.py"

# Update Info.plist:
# LSUIElement = 1 makes it an invisible background agent (NO Dock icon clutter!)
PLIST_PATH="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName FlowBridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Flow Bridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.flowbridge.app" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST_PATH" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST_PATH" 2>/dev/null || true

# 3. Create distributable DMG with classic drag-and-drop layout
echo "📦 Packaging into distributable Drag-and-Drop DMG..."
DMG_STAGING="$DIST_DIR/dmg_staging"
mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"

# Add Applications shortcut link
ln -s /Applications "$DMG_STAGING/Applications"

# Set DMG volume icon and background layout instructions
cat <<EOF > "$DMG_STAGING/Install Instructions.txt"
Flow Bridge - Drag & Drop Installation
======================================

1. Drag FlowBridge.app into the Applications folder shortcut.
2. Open Applications and double-click FlowBridge.app once.
3. That's it! It runs silently in the background and auto-starts on login.
EOF

hdiutil create -volname "Flow Bridge" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_PATH"
rm -rf "$DMG_STAGING"

echo ""
echo "✅ Build Complete!"
echo "   • Application Bundle : $APP_PATH"
echo "   • Distributable DMG  : $DMG_PATH"
