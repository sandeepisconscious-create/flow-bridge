#!/usr/bin/env bash
# ==============================================================================
# Build FlowBridge.app and FlowBridge-Installer.dmg
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
APP_NAME="FlowBridge.app"
APP_PATH="$DIST_DIR/$APP_NAME"
DMG_NAME="FlowBridge-Installer.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

echo "🔨 Building FlowBridge macOS Application bundle..."

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 1. Compile AppleScript launcher into a macOS Application bundle (.app)
APPLESCRIPT_SOURCE="
on run
    set scriptDir to (POSIX path of (path to me)) & \"Contents/Resources/wispr_clipboard_sync.py\"
    set pyBin to do shell script \"which python3 || echo /usr/bin/python3\"
    
    set dialogResult to display dialog \"Flow Bridge will now run in the background to sync your voice dictation (Wispr Flow & Detta) to your clipboard.\\n\\nWould you like to install it as a background service that starts automatically whenever you log in?\" with title \"Flow Bridge Setup\" buttons {\"Run Now Only\", \"Install on Startup\"} default button \"Install on Startup\" with icon note
    
    if button returned of dialogResult is \"Install on Startup\" then
        do shell script quoted form of pyBin & \" \" & quoted form of scriptDir & \" --install-service\"
        display notification \"Flow Bridge has been installed to start automatically on login!\" with title \"Flow Bridge\" subtitle \"Startup Service Enabled\"
    else
        do shell script \"nohup \" & quoted form of pyBin & \" \" & quoted form of scriptDir & \" >/dev/null 2>&1 &\"
        display notification \"Flow Bridge is running in the background for this session!\" with title \"Flow Bridge\" subtitle \"Active\"
    end if
end run
"

osacompile -e "$APPLESCRIPT_SOURCE" -o "$APP_PATH"

# 2. Bundle the python sync engine inside the app's Resources directory
RESOURCES_DIR="$APP_PATH/Contents/Resources"
mkdir -p "$RESOURCES_DIR"
cp "$SCRIPT_DIR/wispr_clipboard_sync.py" "$RESOURCES_DIR/wispr_clipboard_sync.py"
chmod +x "$RESOURCES_DIR/wispr_clipboard_sync.py"

# Update Info.plist to mark as lightweight agent app
PLIST_PATH="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName FlowBridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Flow Bridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.flowbridge.app" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0" "$PLIST_PATH" 2>/dev/null || true

# 3. Create distributable .dmg using hdiutil
echo "📦 Packaging into distributable DMG: $DMG_PATH..."
DMG_STAGING="$DIST_DIR/dmg_staging"
mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"

# Add link to Applications folder for standard Mac installation
ln -s /Applications "$DMG_STAGING/Applications"

# Add README for users opening the DMG
cat <<EOF > "$DMG_STAGING/READ_ME.txt"
Flow Bridge - Universal Voice Dictation Clipboard Sync
=====================================================

Installation:
1. Drag 'FlowBridge.app' into your 'Applications' folder.
2. Double-click 'FlowBridge.app' in Applications to launch or enable startup on boot.
3. Speak into Wispr Flow or Detta, and press ⌘+V anywhere!
EOF

hdiutil create -volname "Flow Bridge Installer" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_PATH"
rm -rf "$DMG_STAGING"

echo ""
echo "✅ Build Complete!"
echo "   • Application Bundle : $APP_PATH"
echo "   • Distributable DMG  : $DMG_PATH"
