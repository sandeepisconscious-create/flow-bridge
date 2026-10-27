"""
Flow Bridge HTTP UI Server and API Handler.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flow_bridge_core.daemon import FlowBridgeDaemon


def start_ui_server(daemon: FlowBridgeDaemon, port: int = 49231) -> ThreadingHTTPServer:
    """Starts a lightweight local HTTP server for the dashboard UI."""
    core_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(core_dir)
    home_app_dir = os.path.expanduser("~/.flow-bridge")
    
    # Candidate UI paths in order of preference
    ui_candidates = [
        os.path.join(parent_dir, "ui"),
        os.path.join(home_app_dir, "ui"),
        os.path.join(os.path.dirname(parent_dir), "ui"),
    ]
    ui_dir = next((p for p in ui_candidates if os.path.exists(os.path.join(p, "index.html"))), ui_candidates[0])

    # Candidate Logo paths in order of preference
    logo_candidates = [
        os.path.join(ui_dir, "favicon.png"),
        os.path.join(parent_dir, "assets", "logo.png"),
        os.path.join(home_app_dir, "assets", "logo.png"),
        os.path.join(os.path.dirname(parent_dir), "assets", "logo.png"),
    ]
    logo_path = next((p for p in logo_candidates if os.path.exists(p)), logo_candidates[0])

    class UIHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Keep terminal output completely silent and clean

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                html_file = os.path.join(ui_dir, "index.html")
                if os.path.exists(html_file):
                    with open(html_file, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            elif self.path in ("/assets/logo.png", "/logo.png", "/favicon.ico", "/favicon.png", "/apple-touch-icon.png"):
                target_file = logo_path
                if self.path in ("/favicon.ico", "/favicon.png"):
                    fav = os.path.join(ui_dir, "favicon.png")
                    if os.path.exists(fav):
                        target_file = fav
                if os.path.exists(target_file):
                    with open(target_file, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            elif self.path == "/api/state":
                data = {
                    "version": daemon.version,
                    "paused": daemon.is_paused(),
                    "auto_pause_media": daemon.config.auto_pause_media,
                    "hide_apps_to_menu_bar": daemon.config.hide_apps_to_menu_bar,
                    "apps": daemon.get_app_status(),
                    "history": daemon.get_recent_history(limit=25),
                    "update": daemon.check_for_update()
                }
                body = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/toggle-pause":
                new_state = daemon.set_paused(not daemon.is_paused())
                body = json.dumps({"paused": new_state}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/toggle-media-pause":
                daemon.config.auto_pause_media = not daemon.config.auto_pause_media
                body = json.dumps({"auto_pause_media": daemon.config.auto_pause_media}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/toggle-dock-hide":
                daemon.config.hide_apps_to_menu_bar = not daemon.config.hide_apps_to_menu_bar
                body = json.dumps({"hide_apps_to_menu_bar": daemon.config.hide_apps_to_menu_bar}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/check-update":
                info = daemon.check_for_update(force=True)
                body = json.dumps(info).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            elif self.path == "/api/auto-update":
                res = daemon.perform_auto_update()
                body = json.dumps(res).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

                if res.get("success"):
                    def do_restart():
                        time.sleep(1.0)
                        # Exit current process; launchd KeepAlive=true will immediately restart with the updated code
                        os._exit(0)
                    threading.Thread(target=do_restart, daemon=True).start()
                return

            elif self.path == "/api/quit":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "quitting"}).encode("utf-8"))
                def do_quit():
                    time.sleep(0.3)
                    daemon.stop()
                    # Also quit any running native FlowBridge macOS app wrapper
                    try:
                        subprocess.run(["pkill", "-f", "FlowBridge.app/Contents/MacOS/FlowBridge"], capture_output=True)
                    except Exception:
                        pass
                    # Unload launchd service so it doesn't instantly resurrect
                    try:
                        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.flowbridge.clipboard.sync.plist")
                        if os.path.exists(plist_path):
                            subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                    except Exception:
                        pass
                    os._exit(0)
                threading.Thread(target=do_quit, daemon=True).start()
                return

            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), UIHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
