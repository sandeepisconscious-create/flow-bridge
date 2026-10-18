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

echo -e "${BOLD}Uninstalling Flow Bridge...${NC}"

# Unload launchd agent
if [[ -f "$PLIST_FILE" ]]; then
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo -e " • Removed background service plist."
fi

# Remove installation directory
if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    echo -e " • Removed $INSTALL_DIR directory."
fi

echo -e "\n${BOLD}${GREEN}✅ Flow Bridge has been completely uninstalled.${NC}\n"
