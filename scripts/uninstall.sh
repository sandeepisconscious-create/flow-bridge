#!/usr/bin/env bash
# ==============================================================================
# Flow Bridge: Uninstaller for macOS
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="$HOME/.flow-bridge"
PLIST_FILE="$HOME/Library/LaunchAgents/com.flowbridge.clipboard.sync.plist"
APP_DIR="/Applications/FlowBridge.app"
USER_APP_DIR="$HOME/Applications/FlowBridge.app"
LOG_OUT="$HOME/Library/Logs/flow_bridge.log"
LOG_ERR="$HOME/Library/Logs/flow_bridge_error.log"

echo -e "${BOLD}Uninstalling Flow Bridge...${NC}"

# 1. Stop running processes
echo -e " • Stopping running Flow Bridge processes..."
pkill -f "FlowBridge.app/Contents/MacOS/FlowBridge" 2>/dev/null || true
pkill -f "flow_bridge.py" 2>/dev/null || true

# 2. Unload and remove LaunchAgent
if [[ -f "$PLIST_FILE" ]]; then
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo -e " • Unloaded and removed background LaunchAgent ($PLIST_FILE)."
fi

# 3. Remove application bundles
if [[ -d "$APP_DIR" ]]; then
    rm -rf "$APP_DIR"
    echo -e " • Removed application from $APP_DIR."
fi
if [[ -d "$USER_APP_DIR" ]]; then
    rm -rf "$USER_APP_DIR"
    echo -e " • Removed application from $USER_APP_DIR."
fi

# 4. Remove support directory (~/.flow-bridge)
if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    echo -e " • Removed $INSTALL_DIR directory."
fi

# 5. Clean up log files
rm -f "$LOG_OUT" "$LOG_ERR"

echo -e "\n${BOLD}${GREEN}✅ Flow Bridge has been completely and cleanly uninstalled from your Mac.${NC}\n"
