# QuickLingo

**Select text anywhere. Press hotkey. Get instant translation.**

A lightweight Windows system tray translation tool that supports **DeepL** and **Google Translate**.  
No browser needed — just a hotkey and a popup right next to your cursor.

---

## Features

| Feature | Description |
|---------|-------------|
| **Dual Engine** | DeepL API and Google Translate (free, no API key needed) |
| **Smart Hotkey** | Sequential key combos like `Ctrl+C, C` or `Ctrl+C, Ctrl+C` |
| **Instant Popup** | Shows loading state immediately, fills translation when ready |
| **Mouse-Anchored** | Popup appears right next to your cursor |
| **Resizable Popup** | Drag any edge or corner to resize (8-direction support, min 600x280) |
| **Right-Click Menu** | Copy All / Copy Selection / Select All on both text panels |
| **DeepL Usage Tracking** | Live API quota display with color-coded progress bar |
| **Dark / Light / System** | Matches your Windows appearance automatically |
| **30+ Languages** | Full language support including CJK, Arabic, Thai, and more |
| **Borderless & Draggable** | Clean modern UI with custom title bar |
| **System Tray** | Runs silently in the background |
| **Windows Autostart** | Optional launch on boot |
| **Single Instance** | Mutex-based duplicate prevention |

---

## Quick Start

### Option 1: Build EXE (Recommended)

**Requirements:** Python 3.9+ on Windows 10/11

```bash
git clone https://github.com/dbswhdrbs/QuickLingo.git
cd QuickLingo

# Double-click build.bat, or run manually:
pip install -r requirements.txt
python -m PyInstaller --onefile --noconsole --name "QuickLingo" translator.py
```

The EXE will be at `dist/QuickLingo.exe`.

### Option 2: Run from Source

```bash
pip install -r requirements.txt
pythonw translator.py
```

> `pythonw` runs Python without a console window. Use `python` instead if you want to see debug output in the terminal.

---

## How to Use

1. **Launch** QuickLingo — a blue **Q** icon appears in the system tray
2. **First run** opens Settings automatically — configure your engine and API key
3. **Select any text** in any application
4. **Press your hotkey** (default: `Ctrl+C` then quickly tap `C`)
5. **Translation popup** appears next to your mouse cursor
6. **Resize** by dragging any edge or corner of the popup
7. **Right-click** on either text panel for Copy All / Copy Selection / Select All
8. Press **Esc** to close, or click **Copy Translation**

---

## Configuration

Right-click the tray icon > **Settings** to configure.

### Translation Engine

| Engine | API Key | Notes |
|--------|:---:|-------|
| **Google Translate** | Not required | Uses free endpoint, works immediately |
| **DeepL** | Required | Higher quality, get free key at [deepl.com/pro-api](https://www.deepl.com/pro-api) |

DeepL offers a **free tier** with 500,000 characters/month.  
Your current usage is displayed in both the **translation popup** (auto) and **Settings** (click "Check").

### Hotkey Presets

| Preset | How to Trigger | Auto-Copies |
|--------|---------------|:---:|
| `Ctrl+C, C` | Copy with Ctrl+C, then tap C quickly | Yes |
| `Ctrl+C, Ctrl+C` | Press Ctrl+C twice quickly | Yes |
| `Ctrl+Shift+T` | Single combo (copy text first) | No |
| `Ctrl+Shift+D` | Single combo (copy text first) | No |
| `Ctrl+Q, Q` | Ctrl+Q then tap Q quickly | No |

> **Tip:** "Auto-Copies" hotkeys include a copy action — just select text and press. Others require Ctrl+C first.

### Theme

| Option | Behavior |
|--------|----------|
| **System** | Follows Windows dark/light mode (reads registry `AppsUseLightTheme`) |
| **Light** | Always light theme |
| **Dark** | Always dark theme |

### All Settings

Stored at `%APPDATA%\QuickLingo\config.json`:

```json
{
  "engine": "deepl",
  "api_key": "your-deepl-key-here",
  "api_type": "free",
  "source_lang": "auto",
  "target_lang": "KO",
  "hotkey": "Ctrl+C, C",
  "hotkey_interval": 0.5,
  "theme": "system",
  "autostart": true
}
```

---

## Supported Languages

<details>
<summary>Click to expand full language list</summary>

### Source Languages (Auto Detect + 30 languages)
Arabic, Bulgarian, Chinese, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Latvian, Lithuanian, Norwegian, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

### Target Languages (32 options)
All source languages plus regional variants:
- English (US) / English (UK)
- Portuguese (Brazil) / Portuguese (Portugal)
- Chinese Simplified / Chinese Traditional

</details>

---

## Architecture

```
QuickLingo (Single file: translator.py)
|
+-- App                       # Main controller
|   +-- HotkeyDetector        # Global keyboard listener (pynput)
|   |   +-- Sequential key combo state machine
|   |   +-- Virtual Key Code resolution (key.vk)
|   +-- TranslationPopup      # Borderless popup window (tkinter)
|   |   +-- Two-phase rendering (loading -> result)
|   |   +-- 8-direction edge/corner resize
|   |   +-- Right-click context menu (Copy All/Selection)
|   |   +-- DeepL usage progress bar
|   +-- SettingsWindow         # Configuration UI with live usage check
|   +-- System Tray Icon       # pystray + Pillow
|
+-- Translation Engines
|   +-- translate_deepl()      # DeepL REST API (Free/Pro)
|   +-- translate_google()     # Google Translate free endpoint
|   +-- get_deepl_usage()      # DeepL /v2/usage quota tracking
|
+-- Theme System
|   +-- Light theme (20+ color variables)
|   +-- Dark theme
|   +-- System detection (Windows registry)
|
+-- Threading Model
    +-- Main Thread            # tkinter mainloop, all UI
    +-- Tray Thread            # pystray event loop
    +-- Listener Thread        # pynput keyboard events
    +-- Translation Thread     # Per-request API call
```

### Key Design Decisions

**Why `pynput` instead of `keyboard`?**  
The `keyboard` library crashed on Python 3.13. `pynput` is more stable across Python versions.

**Why `key.vk` instead of `key.char`?**  
When Ctrl is held, `key.char` returns control characters (`\x03` for C). `key.vk` (Virtual Key Code) gives the correct physical key regardless of modifiers.

**Why two-phase popup rendering?**  
API calls take 300-1000ms. Showing "Translating..." immediately and filling results later makes the app feel instant.

**Why recursive resize binding?**  
`overrideredirect(True)` removes OS resize handles. Edge detection via `win.bind()` only works on exposed window areas — child widgets (title bar, buttons) block events. Binding recursively to all children with screen-absolute coordinate conversion solves this.

**Why `root.after(0, ...)`?**  
tkinter is not thread-safe. All UI updates from background threads must go through `root.after()`. Violating this causes random crashes.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| [pynput](https://pypi.org/project/pynput/) | >= 1.7.6 | Global keyboard event detection |
| [requests](https://pypi.org/project/requests/) | >= 2.28.0 | HTTP client for translation APIs |
| [pystray](https://pypi.org/project/pystray/) | >= 0.19.4 | System tray icon and menu |
| [Pillow](https://pypi.org/project/Pillow/) | >= 9.0.0 | Tray icon image generation |
| [PyInstaller](https://pypi.org/project/pyinstaller/) | >= 6.0.0 | EXE packaging (build only) |
| tkinter | (stdlib) | GUI framework |
| ctypes | (stdlib) | Win32 API (mouse pos, key simulation, mutex) |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hotkey doesn't work in some apps | Run `QuickLingo.exe` as Administrator |
| "Already running" message | Check system tray for existing instance, quit it first |
| DeepL translation fails | Verify API key and plan type (Free/Pro use different endpoints) |
| Google translation fails | Free endpoint may rate-limit heavy usage; try DeepL |
| Popup stuck on "Translating..." | Check `%APPDATA%\QuickLingo\debug.log` for errors |
| Vertical resize not working | Update to v2.2+ (fixed recursive resize binding) |
| Build fails | Use `python -m PyInstaller` instead of `pyinstaller` directly |

---

## File Structure

```
QuickLingo/
+-- translator.py       # Main application (single file, ~1300 lines)
+-- requirements.txt    # Python dependencies
+-- build.bat           # One-click Windows build script
+-- README.md           # This file
+-- LICENSE             # MIT License
+-- .gitignore          # Excludes build artifacts and config
```

Runtime files (auto-created):
```
%APPDATA%/QuickLingo/
+-- config.json         # User settings (API key, theme, hotkey, etc.)
+-- debug.log           # Debug log for troubleshooting
```

---

## Changelog

### v2.2.0
- Resizable popup (drag any edge or corner, 8-direction, min 600x280)
- Right-click context menu on text panels (Copy All / Copy Selection / Select All)
- Mouse text selection support in disabled Text widgets
- Recursive resize event binding for borderless windows
- Resize grip indicator at bottom-right corner

### v2.1.0
- DeepL API usage tracking (`/v2/usage` endpoint)
- Usage progress bar in translation popup (auto-displayed after DeepL translation)
- Usage check button in Settings with color-coded bar (blue/orange/red)
- Fixed `tk.Frame` pady tuple crash (moved theme init to method start)
- Enhanced error logging with full traceback in all critical paths

### v2.0.0
- Dual engine support: DeepL API + Google Translate (free)
- Dark / Light / System theme with 20+ color variables
- Two-phase popup rendering (instant loading state)
- Borderless draggable popup with custom title bar
- Modern card-based Settings UI with dynamic engine section
- Apple-style color palette

### v1.1.0
- Migrated from `keyboard` to `pynput` (Python 3.13 stability)
- Virtual Key Code (`key.vk`) for reliable Ctrl+key detection
- Configurable hotkey presets (5 options)
- Comprehensive debug logging to file
- Safe clipboard access via tkinter

### v1.0.0
- Initial release
- DeepL translation with Ctrl+C double-press
- System tray with settings
- Windows autostart

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## Acknowledgments

- [DeepL API](https://www.deepl.com/docs-api) for high-quality machine translation
- [Google Translate](https://translate.google.com/) for free, accessible translation
- Built with Python
