#!/usr/bin/env bash
# ==============================================================================
# Build FlowBridge.app and FlowBridge-Installer.dmg with custom icons & layout
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
APP_NAME="FlowBridge.app"
APP_PATH="$DIST_DIR/$APP_NAME"
DMG_NAME="FlowBridge-Installer.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
ICON_PATH="$REPO_ROOT/assets/FlowBridge.icns"

echo "🔨 Building FlowBridge macOS Application bundle..."

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 1. Compile AppleScript launcher into a macOS Application bundle (.app)
APPLESCRIPT_SOURCE="
on run
    set appDir to (POSIX path of (path to me))
    set scriptDir to appDir & \"Contents/Resources/flow_bridge.py\"
    set uiDir to appDir & \"Contents/Resources/ui\"
    set pyBin to do shell script \"which python3 || echo /usr/bin/python3\"
    set userHome to (POSIX path of (path to home folder))
    set targetDir to userHome & \".flow-bridge\"
    set targetScript to targetDir & \"/flow_bridge.py\"
    set targetUI to targetDir & \"/ui\"
    
    -- Auto-install into ~/.flow-bridge
    do shell script \"mkdir -p \" & quoted form of targetDir & \" && cp \" & quoted form of scriptDir & \" \" & quoted form of targetScript & \" && cp -R \" & quoted form of uiDir & \" \" & quoted form of targetDir & \" && chmod +x \" & quoted form of targetScript
    
    -- Register LaunchAgent service to start on boot
    do shell script quoted form of pyBin & \" \" & quoted form of targetScript & \" --install-service\"
    
    -- Open Dashboard UI
    do shell script \"open http://127.0.0.1:49231\"
    display notification \"Flow Bridge is active! Showing your dictation dashboard.\" with title \"Flow Bridge\" subtitle \"Dictation Hub Active\"
end run
"

osacompile -e "$APPLESCRIPT_SOURCE" -o "$APP_PATH"

# 2. Bundle python sync engine and UI dashboard inside the app's Resources directory
RESOURCES_DIR="$APP_PATH/Contents/Resources"
mkdir -p "$RESOURCES_DIR"
cp "$REPO_ROOT/flow_bridge.py" "$RESOURCES_DIR/flow_bridge.py"
cp -R "$REPO_ROOT/ui" "$RESOURCES_DIR/ui"
chmod +x "$RESOURCES_DIR/flow_bridge.py"

# Apply custom app icon (.icns)
if [[ -f "$ICON_PATH" ]]; then
    echo " • Applying FlowBridge.icns custom app icon..."
    cp "$ICON_PATH" "$RESOURCES_DIR/applet.icns"
    cp "$ICON_PATH" "$RESOURCES_DIR/FlowBridge.icns"
fi

# Update Info.plist:
# LSUIElement = 1 makes it an invisible background agent (NO Dock icon clutter!)
PLIST_PATH="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName FlowBridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Flow Bridge" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.flowbridge.app" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile FlowBridge.icns" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string FlowBridge.icns" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST_PATH" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST_PATH" 2>/dev/null || true

# Strip metadata detritus and apply clean ad-hoc code signature
echo " • Signing FlowBridge.app bundle..."
xattr -cr "$APP_PATH" 2>/dev/null || true
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || true

# Refresh bundle icon cache
touch "$APP_PATH"

# 3. Create writable DMG staging image
echo "📦 Packaging into distributable Drag-and-Drop DMG..."
DMG_TEMP="$DIST_DIR/temp.dmg"
rm -f "$DMG_TEMP" "$DMG_PATH"

# Create temporary writable DMG
hdiutil create -size 32m -fs HFS+ -volname "Flow Bridge" "$DMG_TEMP"

# Mount temporary DMG
MOUNT_DIR=$(hdiutil attach -readwrite -noverify -noautoopen "$DMG_TEMP" | grep -o '/Volumes/Flow Bridge.*' | head -n 1)

if [[ -z "$MOUNT_DIR" || ! -d "$MOUNT_DIR" ]]; then
    echo "Failed to mount staging DMG." >&2
    exit 1
fi

echo " • Mounted at: $MOUNT_DIR"

# Copy App and link Applications folder
cp -R "$APP_PATH" "$MOUNT_DIR/"
ln -s /Applications "$MOUNT_DIR/Applications"

# Set volume icon if available
if [[ -f "$ICON_PATH" ]]; then
    cp "$ICON_PATH" "$MOUNT_DIR/.VolumeIcon.icns"
    # Set custom icon flag on volume root
    SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
fi

# 4. Use AppleScript to style the Finder window (140px icons, side-by-side, compact 560x360 window)
echo " • Configuring Finder window layout..."
osascript <<EOF || true
tell application "Finder"
    tell disk "Flow Bridge"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {400, 200, 960, 560}
        
        set viewOptions to the icon view options of container window
        set icon size of viewOptions to 128
        set text size of viewOptions to 13
        set label position of viewOptions to bottom
        set arrangement of viewOptions to not arranged
        
        -- Place FlowBridge on the left, Applications on the right
        set position of item "FlowBridge.app" of container window to {140, 160}
        set position of item "Applications" of container window to {420, 160}
        
        close
        open
        delay 1
    end tell
end tell
EOF

# Sync and unmount
sync
diskutil eject "$MOUNT_DIR" || hdiutil detach "$MOUNT_DIR" -force

# 5. Convert to compressed, read-only final DMG
echo " • Compressing into final UDZO DMG..."
hdiutil convert "$DMG_TEMP" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$DMG_TEMP"

echo ""
echo "✅ Build Complete!"
echo "   • Application Bundle : $APP_PATH"
echo "   • Distributable DMG  : $DMG_PATH"
