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

# 1. Build Native Cocoa Application Bundle (bypasses osacompile default icon asset catalog)
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

cat <<'EOF' > "$DIST_DIR/launcher.m"
#import <Cocoa/Cocoa.h>
#import <Foundation/Foundation.h>

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSFileManager *fm = [NSFileManager defaultManager];
        NSString *home = NSHomeDirectory();
        NSString *targetDir = [home stringByAppendingPathComponent:@".flow-bridge"];
        NSString *targetScript = [targetDir stringByAppendingPathComponent:@"flow_bridge.py"];
        NSString *targetUI = [targetDir stringByAppendingPathComponent:@"ui"];
        
        NSString *bundleRes = [[NSBundle mainBundle] resourcePath];
        NSString *srcScript = [bundleRes stringByAppendingPathComponent:@"flow_bridge.py"];
        NSString *srcUI = [bundleRes stringByAppendingPathComponent:@"ui"];
        
        // 1. Create ~/.flow-bridge
        [fm createDirectoryAtPath:targetDir withIntermediateDirectories:YES attributes:nil error:nil];
        
        // 2. Copy flow_bridge.py & ui
        if ([fm fileExistsAtPath:srcScript]) {
            [fm removeItemAtPath:targetScript error:nil];
            [fm copyItemAtPath:srcScript toPath:targetScript error:nil];
            NSDictionary *perms = @{NSFilePosixPermissions: @0755};
            [fm setAttributes:perms ofItemAtPath:targetScript error:nil];
        }
        if ([fm fileExistsAtPath:srcUI]) {
            [fm removeItemAtPath:targetUI error:nil];
            [fm copyItemAtPath:srcUI toPath:targetUI error:nil];
        }
        
        // 3. Register launchd background service
        NSTask *task = [[NSTask alloc] init];
        task.launchPath = @"/bin/bash";
        task.arguments = @[@"-c", [NSString stringWithFormat:@"python3 '%@' --install-service", targetScript]];
        [task launch];
        [task waitUntilExit];
        
        // 4. Open UI Dashboard
        [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:@"http://127.0.0.1:49231"]];
    }
    return 0;
}
EOF

echo " • Compiling native FlowBridge launcher executable..."
clang -O3 -framework Cocoa -o "$APP_PATH/Contents/MacOS/FlowBridge" "$DIST_DIR/launcher.m"
rm -f "$DIST_DIR/launcher.m"

# 2. Bundle python sync engine, UI dashboard, and custom icon
RESOURCES_DIR="$APP_PATH/Contents/Resources"
cp "$REPO_ROOT/flow_bridge.py" "$RESOURCES_DIR/flow_bridge.py"
cp -R "$REPO_ROOT/ui" "$RESOURCES_DIR/ui"
chmod +x "$RESOURCES_DIR/flow_bridge.py"

if [[ -f "$ICON_PATH" ]]; then
    echo " • Installing custom FlowBridge.icns..."
    cp "$ICON_PATH" "$RESOURCES_DIR/FlowBridge.icns"
fi

# Clean Info.plist with explicit icon and background agent configuration
cat <<EOF > "$APP_PATH/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>FlowBridge</string>
    <key>CFBundleDisplayName</key>
    <string>Flow Bridge</string>
    <key>CFBundleIdentifier</key>
    <string>com.flowbridge.app</string>
    <key>CFBundleVersion</key>
    <string>1.0.3</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.3</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>FlowBridge</string>
    <key>CFBundleIconFile</key>
    <string>FlowBridge</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

# Strip metadata detritus and apply clean ad-hoc code signature
echo " • Signing native FlowBridge.app bundle..."
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

# Add a 1-click double-clickable Launch script inside the DMG that automatically un-quarantines and opens
cat <<'HELPER_EOF' > "$MOUNT_DIR/Open FlowBridge.command"
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="/Applications/FlowBridge.app"

if [[ ! -d "$APP" ]]; then
    echo "Copying FlowBridge to /Applications..."
    cp -R "$DIR/FlowBridge.app" /Applications/
fi

echo "Activating FlowBridge..."
xattr -cr "$APP" 2>/dev/null || true
open "$APP"
exit 0
HELPER_EOF
chmod +x "$MOUNT_DIR/Open FlowBridge.command"

# Set volume icon if available
if [[ -f "$ICON_PATH" ]]; then
    cp "$ICON_PATH" "$MOUNT_DIR/.VolumeIcon.icns"
    # Set custom icon flag on volume root
    SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
fi

# 4. Use AppleScript to style the Finder window (side-by-side, compact window)
echo " • Configuring Finder window layout..."
osascript <<EOF || true
tell application "Finder"
    tell disk "Flow Bridge"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {360, 200, 960, 560}
        
        set viewOptions to the icon view options of container window
        set icon size of viewOptions to 110
        set text size of viewOptions to 12
        set label position of viewOptions to bottom
        set arrangement of viewOptions to not arranged
        
        -- Place FlowBridge on the left, Applications in the middle, Open FlowBridge on the right
        set position of item "FlowBridge.app" of container window to {120, 160}
        set position of item "Applications" of container window to {320, 160}
        set position of item "Open FlowBridge.command" of container window to {490, 160}
        
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
