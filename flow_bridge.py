#!/usr/bin/env python3
"""
Flow Bridge: Universal Voice Dictation Clipboard Sync Daemon
- Concurrently monitors Wispr Flow, Handy, and Detta voice dictation databases.
- Auto-detects newly transcribed speech across voice apps with millisecond timestamps.
- Instantly places the latest dictation onto the macOS GUI session clipboard (NSPasteboard).
- Employs anti-race settle & hold protection so neither app's internal cleanup / simulated paste can overwrite your transcript.
- Supports native macOS notifications, custom poll intervals, launchd service generation, and CLI diagnostics.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# Ensure flow_bridge_core package is importable when executed directly
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flow_bridge_core.daemon import FlowBridgeDaemon
from flow_bridge_core.models import CURRENT_VERSION, DaemonConfig, DictationRecord
from flow_bridge_core.platform.pasteboard import Notifier, PasteboardManager
from flow_bridge_core.platform.shortcut import ShortcutWatcher
from flow_bridge_core.watchers.engines import BaseDictationWatcher, DettaWatcher, HandyWatcher, WisprFlowWatcher


def generate_launchd_plist() -> str:
    """Generates a macOS launchd user agent plist for running Flow Bridge on login."""
    script_path = os.path.abspath(__file__)
    dir_path = os.path.dirname(script_path)
    launcher_path = os.path.join(dir_path, "FlowBridge")
    home = os.path.expanduser("~")

    # If launcher binary doesn't exist, compile it via clang so macOS shows "FlowBridge" in Login Items
    if not os.path.exists(launcher_path):
        c_src = f"""#include <unistd.h>
#include <stdlib.h>
int main(int argc, char *argv[]) {{
    char *args[] = {{"{sys.executable}", "{script_path}", NULL}};
    execv("{sys.executable}", args);
    return 1;
}}
"""
        c_file = os.path.join(dir_path, "_launcher.c")
        try:
            with open(c_file, "w") as f:
                f.write(c_src)
            subprocess.run(["clang", "-O2", c_file, "-o", launcher_path], check=True, capture_output=True)
            subprocess.run(["codesign", "-s", "-", "--force", "--identifier", "com.flowbridge.launcher", launcher_path], capture_output=True)
            os.remove(c_file)
        except Exception:
            pass

    # Attach custom app icon to FlowBridge binary so macOS Settings displays custom icon instead of terminal exec icon
    icon_src = os.path.join(dir_path, "assets", "FlowBridge.icns")
    if os.path.exists(launcher_path) and os.path.exists(icon_src):
        objc_icon_script = f"""#import <Cocoa/Cocoa.h>
int main(void) {{
    @autoreleasepool {{
        NSImage *img = [[NSImage alloc] initWithContentsOfFile:@"{icon_src}"];
        if (img) {{
            [[NSWorkspace sharedWorkspace] setIcon:img forFile:@"{launcher_path}" options:0];
        }}
    }}
    return 0;
}}
"""
        icon_c_file = os.path.join(dir_path, "_set_icon.m")
        icon_bin = os.path.join(dir_path, "_set_icon")
        try:
            with open(icon_c_file, "w") as f:
                f.write(objc_icon_script)
            subprocess.run(["clang", "-framework", "Cocoa", icon_c_file, "-o", icon_bin], check=True, capture_output=True)
            subprocess.run([icon_bin], check=True, capture_output=True)
            os.remove(icon_c_file)
            os.remove(icon_bin)
        except Exception:
            pass

    if os.path.exists(launcher_path):
        exec_args = f"<string>{launcher_path}</string>"
    else:
        exec_args = f"<string>{sys.executable}</string>\n        <string>{script_path}</string>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.flowbridge.clipboard.sync</string>
    <key>ProgramArguments</key>
    <array>
        {exec_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{home}/Library/Logs/flow_bridge.log</string>
    <key>StandardErrorPath</key>
    <string>{home}/Library/Logs/flow_bridge_error.log</string>
    <key>WorkingDirectory</key>
    <string>{dir_path}</string>
</dict>
</plist>
"""


def install_service() -> None:
    """Installs and starts the launchd agent."""
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(plist_dir, "com.flowbridge.clipboard.sync.plist")
    os.makedirs(plist_dir, exist_ok=True)

    content = generate_launchd_plist()
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(content)

    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
    res = subprocess.run(["launchctl", "load", plist_path], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Successfully installed and loaded Flow Bridge launchd agent:")
        print(f"   {plist_path}")
        print("   It will now automatically run silently in the background on startup.")
    else:
        print(f"⚠️ Installed plist to {plist_path}, but launchctl load returned: {res.stderr}")


def uninstall_service() -> None:
    """Unloads and removes the launchd agent."""
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.flowbridge.clipboard.sync.plist")
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        print("✅ Successfully uninstalled Flow Bridge launchd agent.")
    else:
        print("ℹ️ No installed launchd agent found.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flow Bridge: Universal Voice Dictation Clipboard Sync Daemon",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--poll", type=float, default=0.25, help="Poll interval in seconds")
    parser.add_argument("--settle", type=float, default=0.35, help="Settle delay before re-assertion")
    parser.add_argument("--reassert", type=int, default=3, help="Number of re-assert attempts")
    parser.add_argument("--notify", action="store_true", help="Display native macOS notification on sync")
    parser.add_argument("--verbose", action="store_true", help="Print verbose debug logs")
    parser.add_argument("--install-service", action="store_true", help="Install as macOS background launchd service (runs on boot)")
    parser.add_argument("--uninstall-service", action="store_true", help="Uninstall macOS background launchd service")
    parser.add_argument("--test-clipboard", action="store_true", help="Test setting clipboard and exit")
    parser.add_argument("--dashboard", action="store_true", help="Open Flow Bridge shadcn/ui dashboard")

    args = parser.parse_args()

    if args.dashboard:
        subprocess.run(["open", "http://127.0.0.1:49231"])
        return

    if args.install_service:
        install_service()
        return

    if args.uninstall_service:
        uninstall_service()
        return

    if args.test_clipboard:
        test_str = "Flow Bridge Clipboard Test OK"
        success = PasteboardManager.set_clipboard(test_str)
        curr = PasteboardManager.get_clipboard()
        print(f"Set clipboard result: {success}, Current pasteboard content: '{curr}'")
        return

    config = DaemonConfig(
        poll_interval_sec=args.poll,
        settle_delay_sec=args.settle,
        reassert_attempts=args.reassert,
        show_notifications=args.notify,
        verbose=args.verbose
    )

    daemon = FlowBridgeDaemon(config)
    daemon.run()


if __name__ == "__main__":
    main()
