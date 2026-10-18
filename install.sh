#!/usr/bin/env bash
# ==============================================================================
# Flow Bridge: Universal Voice Dictation Clipboard Sync Installer for macOS
# Repo: https://github.com/sandeepisconscious-create/flow-bridge
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

INSTALL_DIR="$HOME/.flow-bridge"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$LAUNCH_AGENTS_DIR/com.flowbridge.clipboard.sync.plist"
RAW_BASE_URL="https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main"

echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║       🎙️  Flow Bridge: Universal Voice Clipboard Installer      ║${NC}"
echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"

# 1. macOS Check
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}[Error] Flow Bridge is designed specifically for macOS.${NC}" >&2
    exit 1
fi

# 2. Python3 Check
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[Error] Python 3 is required. Please install Xcode Command Line Tools or Python 3.${NC}" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3)"
echo -e " • Using Python runtime: ${GREEN}$PYTHON_BIN${NC}"

# 3. Create install directory
mkdir -p "$INSTALL_DIR"
mkdir -p "$LAUNCH_AGENTS_DIR"

# 4. Download or copy daemon script and UI dashboard
TARGET_SCRIPT="$INSTALL_DIR/flow_bridge.py"
mkdir -p "$INSTALL_DIR/ui"
mkdir -p "$INSTALL_DIR/assets"

# If running from local clone repo directory
if [[ -f "./flow_bridge.py" ]]; then
    echo -e " • Copying local script to ${BOLD}$TARGET_SCRIPT${NC}..."
    cp "./flow_bridge.py" "$TARGET_SCRIPT"
    cp -R "./flow_bridge_core" "$INSTALL_DIR/" 2>/dev/null || true
    cp -R "./ui/"* "$INSTALL_DIR/ui/" 2>/dev/null || true
    cp -R "./assets/"* "$INSTALL_DIR/assets/" 2>/dev/null || true
else
    echo -e " • Downloading latest Flow Bridge from GitHub..."
    if command -v curl &>/dev/null; then
        curl -fsSL "$RAW_BASE_URL/flow_bridge.py" -o "$TARGET_SCRIPT"
        curl -fsSL "$RAW_BASE_URL/ui/index.html" -o "$INSTALL_DIR/ui/index.html" 2>/dev/null || true
        curl -fsSL "$RAW_BASE_URL/assets/logo.png" -o "$INSTALL_DIR/assets/logo.png" 2>/dev/null || true
    elif command -v wget &>/dev/null; then
        wget -qO "$TARGET_SCRIPT" "$RAW_BASE_URL/flow_bridge.py"
        wget -qO "$INSTALL_DIR/ui/index.html" "$RAW_BASE_URL/ui/index.html" 2>/dev/null || true
        wget -qO "$INSTALL_DIR/assets/logo.png" "$RAW_BASE_URL/assets/logo.png" 2>/dev/null || true
    else
        echo -e "${RED}[Error] Neither curl nor wget found. Cannot download script.${NC}" >&2
        exit 1
    fi
fi

chmod +x "$TARGET_SCRIPT"

# 5. Compile native launcher wrapper binary so macOS displays "FlowBridge"
# instead of generic "python3" in Login Items & Background Activity notifications
LAUNCHER_BIN="$INSTALL_DIR/FlowBridge"
if command -v clang &>/dev/null; then
    echo -e " • Creating native FlowBridge launcher..."
    clang -O2 -x c - -o "$LAUNCHER_BIN" << EOF
#include <unistd.h>
#include <stdlib.h>
int main(int argc, char *argv[]) {
    char *args[] = {"$PYTHON_BIN", "$TARGET_SCRIPT", NULL};
    execv("$PYTHON_BIN", args);
    return 1;
}
EOF
    chmod +x "$LAUNCHER_BIN"
    EXEC_CMD="<string>$LAUNCHER_BIN</string>"
else
    EXEC_CMD="<string>$PYTHON_BIN</string>
        <string>$TARGET_SCRIPT</string>"
fi

# 6. Stop existing launchd agent if running
if launchctl list | grep -q "com.flowbridge.clipboard.sync"; then
    echo -e " • Stopping existing background service..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
fi

# 7. Generate LaunchAgent Plist
echo -e " • Configuring background auto-start service (launchd)..."
cat <<EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.flowbridge.clipboard.sync</string>
    <key>ProgramArguments</key>
    <array>
        $EXEC_CMD
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/flow_bridge.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/flow_bridge_error.log</string>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
</dict>
</plist>
EOF

# 8. Start the service
launchctl load "$PLIST_FILE"

echo -e "\n${BOLD}${GREEN}✅ Flow Bridge is installed and running in the background!${NC}"
echo -e "   • Script location: ${BLUE}$TARGET_SCRIPT${NC}"
echo -e "   • Service plist:   ${BLUE}$PLIST_FILE${NC}"
echo -e "   • Logs:            ${BLUE}$HOME/Library/Logs/flow_bridge.log${NC}\n"
echo -e "${BOLD}How to use:${NC}"
echo -e "   1. Speak into ${BOLD}Wispr Flow${NC} or ${BOLD}Detta${NC} anywhere."
echo -e "   2. Press ${BOLD}⌘ + V${NC} in Google AI Studio, ChatGPT, Claude, Terminal, Slack, etc."
echo -e "   3. Your voice transcript will paste reliably every time.\n"
echo -e "${YELLOW}To uninstall anytime, simply run:${NC}"
echo -e "   curl -fsSL $RAW_BASE_URL/scripts/uninstall.sh | bash\n"
