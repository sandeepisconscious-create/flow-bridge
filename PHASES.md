# Flow Bridge Architecture & RoadMap

## Overview
Flow Bridge has transitioned from fragile in-page DOM manipulation to a **Universal OS-Level Dictation Clipboard Sync Daemon**.

### Problem with In-Page DOM Hacking
1. Complex frameworks (Google AI Studio's Angular/Material stack, ProseMirror, React synthetic events) swallow or reject synthetic input events.
2. Focus drift occurs at the OS window manager level when voice dictation tools activate their audio listener overlays.
3. Continual DOM mutations and class name updates break CSS selectors and cause maintenance overhead.

### Universal Hub Architecture
- **Multi-Engine Ingestion**: Concurrently monitors SQLite WAL transaction logs for both Wispr Flow and Detta.
- **Timestamp Resolution**: Automatically prioritizes the most recent voice utterance based on UTC microsecond timestamps.
- **AppKit NSPasteboard Access**: Directly interfaces with macOS GUI session pasteboard to bypass shell pipe isolation.
- **Settle & Hold Protocol**: Prevents third-party voice apps from restoring stale clipboards during internal cleanup.
- **Background Daemon Management**: Integrated launchd plist generation and uninstallation.
