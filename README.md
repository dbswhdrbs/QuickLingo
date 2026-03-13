# QuickLingo v2.0

Select text anywhere, press your hotkey, and get an instant translation popup.
Supports **DeepL** and **Google Translate**.
<p align="center">
<img width="562" height="756" alt="image" src="https://github.com/user-attachments/assets/e46957ff-8124-4870-90f8-150c92678200" />
</p>

## Features

- **Instant popup** — shows loading state immediately, fills translation when ready
- **DeepL + Google Translate** — choose your engine in settings
- **Dark / Light / System theme** — matches your Windows appearance
- **Configurable hotkey** — Ctrl+C,C / Ctrl+C,Ctrl+C / Ctrl+Shift+T / etc.
- **Mouse-anchored popup** — appears right of your cursor
- **System tray** — runs quietly in the background
- **Windows autostart** — optional boot-time launch
- **Borderless draggable popup** — clean modern UI

---

## Quick Start

### Build EXE
```
Double-click build.bat
```
Output: `dist\QuickLingo.exe`

### Or run directly
```bash
pip install -r requirements.txt
pythonw translator.py
```

---

## Setup

1. Run QuickLingo — blue **Q** icon appears in system tray
2. Right-click tray icon > **Settings**
3. Choose engine:
   - **Google Translate** — works immediately, no API key needed
   - **DeepL** — enter your API key (get one at https://www.deepl.com/pro-api)
4. Set source/target language, hotkey, theme
5. Select text anywhere > press hotkey > translation popup appears

---

## Settings

| Setting | Options |
|---------|---------|
| Engine | DeepL / Google Translate |
| DeepL API Key | Your authentication key |
| DeepL Plan | Free / Pro |
| Source Language | Auto Detect or specific |
| Target Language | 30+ languages |
| Hotkey | 5 presets available |
| Theme | System / Light / Dark |
| Autostart | On / Off |

Config stored at `%APPDATA%\QuickLingo\config.json`

---

## Troubleshooting

- **Debug log**: `%APPDATA%\QuickLingo\debug.log`
- **Hotkey not working in admin apps**: Run QuickLingo as administrator
- **Already running**: Check system tray for existing instance
