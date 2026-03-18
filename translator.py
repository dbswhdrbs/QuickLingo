"""
QuickLingo v2.3
===============
Windows tray-resident translation tool.
Supports DeepL, Google Translate, and Gemini AI.
Configurable hotkey, dark/light/system theme.
"""

import json
import os
import sys
import time
import threading
import logging
import traceback
import ctypes
import ctypes.wintypes
import winreg
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
import pystray
from pynput import keyboard as pynput_kb

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

LOG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "QuickLingo"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "debug.log", encoding="utf-8")],
)
log = logging.getLogger("quicklingo")

# ─────────────────────────────────────────────
# SSL Certificate Fix (PyInstaller temp cleanup)
# ─────────────────────────────────────────────

def _fix_ssl_certs():
    """
    PyInstaller --onefile extracts to Temp\\_MEIxxxxxx.
    If a cleanup tool deletes that folder's certifi/cacert.pem,
    all HTTPS requests fail. Fix: copy certs to AppData on first
    successful run, then fall back to the AppData copy.
    """
    if not getattr(sys, "frozen", False):
        return  # Running from source, no fix needed

    app_cert = LOG_DIR / "cacert.pem"

    # Try to use the bundled certifi cert
    try:
        import certifi
        bundled = certifi.where()
        if os.path.exists(bundled):
            # Cert exists — copy to AppData as backup for next time
            import shutil
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled, str(app_cert))
            return  # All good
    except Exception:
        pass

    # Bundled cert is missing (temp was cleaned) — use the backup
    if app_cert.exists():
        os.environ["REQUESTS_CA_BUNDLE"] = str(app_cert)
        os.environ["SSL_CERT_FILE"] = str(app_cert)
        log.info(f"SSL fix: using backup cert at {app_cert}")
    else:
        log.warning("SSL fix: no backup cert found, HTTPS may fail")

_fix_ssl_certs()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

APP_NAME = "QuickLingo"
APP_VERSION = "2.3.0"
POPUP_MIN_W = 600
POPUP_MIN_H = 280
POPUP_DEFAULT_W = 720
POPUP_DEFAULT_H = 340
POPUP_OFFSET_X = 20
POPUP_OFFSET_Y = -40

CONFIG_DIR = LOG_DIR
CONFIG_FILE = CONFIG_DIR / "config.json"

# ─────────────────────────────────────────────
# Theme System
# ─────────────────────────────────────────────

THEMES = {
    "light": {
        "bg":           "#f5f5f7",
        "bg_secondary": "#ffffff",
        "bg_tertiary":  "#eef2ff",
        "fg":           "#1d1d1f",
        "fg_secondary": "#6e6e73",
        "fg_dim":       "#999999",
        "accent":       "#0071e3",
        "accent_hover": "#0077ed",
        "border":       "#d2d2d7",
        "border_focus": "#0071e3",
        "input_bg":     "#ffffff",
        "btn_bg":       "#0071e3",
        "btn_fg":       "#ffffff",
        "btn_secondary_bg": "#e8e8ed",
        "btn_secondary_fg": "#1d1d1f",
        "card_bg":      "#ffffff",
        "card_bg_alt":  "#f0f5ff",
        "shadow":       "#00000012",
        "success":      "#34c759",
        "error":        "#ff3b30",
        "separator":    "#e5e5ea",
    },
    "dark": {
        "bg":           "#1c1c1e",
        "bg_secondary": "#2c2c2e",
        "bg_tertiary":  "#1e2a3a",
        "fg":           "#f5f5f7",
        "fg_secondary": "#98989d",
        "fg_dim":       "#636366",
        "accent":       "#0a84ff",
        "accent_hover": "#409cff",
        "border":       "#38383a",
        "border_focus": "#0a84ff",
        "input_bg":     "#2c2c2e",
        "btn_bg":       "#0a84ff",
        "btn_fg":       "#ffffff",
        "btn_secondary_bg": "#3a3a3c",
        "btn_secondary_fg": "#f5f5f7",
        "card_bg":      "#2c2c2e",
        "card_bg_alt":  "#1e2d3d",
        "shadow":       "#00000040",
        "success":      "#30d158",
        "error":        "#ff453a",
        "separator":    "#38383a",
    },
}


def detect_system_theme() -> str:
    """Detect Windows dark/light mode from registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if val == 1 else "dark"
    except Exception:
        return "light"


def get_theme(theme_name: str) -> dict:
    if theme_name == "system":
        return THEMES[detect_system_theme()]
    return THEMES.get(theme_name, THEMES["light"])


# ─────────────────────────────────────────────
# Languages
# ─────────────────────────────────────────────

LANGUAGES_SOURCE = {
    "auto": "Auto Detect",
    "BG": "Bulgarian", "CS": "Czech", "DA": "Danish", "DE": "German",
    "EL": "Greek", "EN": "English", "ES": "Spanish", "ET": "Estonian",
    "FI": "Finnish", "FR": "French", "HU": "Hungarian", "ID": "Indonesian",
    "IT": "Italian", "JA": "Japanese", "KO": "Korean",
    "LT": "Lithuanian", "LV": "Latvian", "NB": "Norwegian", "NL": "Dutch",
    "PL": "Polish", "PT": "Portuguese", "RO": "Romanian", "RU": "Russian",
    "SK": "Slovak", "SL": "Slovenian", "SV": "Swedish", "TR": "Turkish",
    "UK": "Ukrainian", "ZH": "Chinese", "AR": "Arabic", "HI": "Hindi",
    "TH": "Thai", "VI": "Vietnamese",
}

LANGUAGES_TARGET = {
    "BG": "Bulgarian", "CS": "Czech", "DA": "Danish", "DE": "German",
    "EL": "Greek", "EN-US": "English (US)", "EN-GB": "English (UK)",
    "ES": "Spanish", "ET": "Estonian", "FI": "Finnish", "FR": "French",
    "HU": "Hungarian", "ID": "Indonesian", "IT": "Italian",
    "JA": "Japanese", "KO": "Korean",
    "LT": "Lithuanian", "LV": "Latvian", "NB": "Norwegian", "NL": "Dutch",
    "PL": "Polish", "PT-BR": "Portuguese (BR)", "PT-PT": "Portuguese (PT)",
    "RO": "Romanian", "RU": "Russian", "SK": "Slovak", "SL": "Slovenian",
    "SV": "Swedish", "TR": "Turkish", "UK": "Ukrainian",
    "ZH-HANS": "Chinese (Simplified)", "ZH-HANT": "Chinese (Traditional)",
    "AR": "Arabic", "HI": "Hindi", "TH": "Thai", "VI": "Vietnamese",
}

# Google uses different language codes
GOOGLE_LANG_MAP = {
    "auto": "auto", "EN-US": "en", "EN-GB": "en", "PT-BR": "pt",
    "PT-PT": "pt", "ZH-HANS": "zh-CN", "ZH-HANT": "zh-TW",
    "NB": "no",
}

def to_google_code(code: str) -> str:
    return GOOGLE_LANG_MAP.get(code, code.lower().split("-")[0])


# ─────────────────────────────────────────────
# Hotkey Presets
# ─────────────────────────────────────────────

HOTKEY_PRESETS = {
    "Ctrl+C, C": {
        "desc": "Ctrl+C then C",
        "steps": [{"mod": ["ctrl"], "key": "c"}, {"mod": [], "key": "c"}],
        "copies": True,
    },
    "Ctrl+C, Ctrl+C": {
        "desc": "Ctrl+C twice",
        "steps": [{"mod": ["ctrl"], "key": "c"}, {"mod": ["ctrl"], "key": "c"}],
        "copies": True,
    },
    "Ctrl+Shift+T": {
        "desc": "Ctrl+Shift+T",
        "steps": [{"mod": ["ctrl", "shift"], "key": "t"}],
        "copies": False,
    },
    "Ctrl+Shift+D": {
        "desc": "Ctrl+Shift+D",
        "steps": [{"mod": ["ctrl", "shift"], "key": "d"}],
        "copies": False,
    },
    "Ctrl+Q, Q": {
        "desc": "Ctrl+Q then Q",
        "steps": [{"mod": ["ctrl"], "key": "q"}, {"mod": [], "key": "q"}],
        "copies": False,
    },
}

DEFAULT_CONFIG = {
    "api_key": "",
    "api_type": "free",
    "engine": "deepl",          # "deepl", "google", or "gemini"
    "google_api_key": "",       # empty = use free endpoint
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "source_lang": "auto",
    "target_lang": "KO",
    "autostart": True,
    "hotkey": "Ctrl+C, C",
    "hotkey_interval": 0.5,
    "theme": "system",          # "light", "dark", "system"
}


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception as e:
            log.error(f"Config load error: {e}")
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────
# Windows Autostart
# ─────────────────────────────────────────────

REG_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

def set_autostart(enable: bool):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe = f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'pythonw.exe "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        log.error(f"Autostart error: {e}")


# ─────────────────────────────────────────────
# Win32 Helpers
# ─────────────────────────────────────────────

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def simulate_copy():
    u = ctypes.windll.user32
    VK_CTRL, VK_C, UP = 0x11, 0x43, 0x0002
    u.keybd_event(VK_CTRL, 0, 0, 0)
    u.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.04)
    u.keybd_event(VK_C, 0, UP, 0)
    u.keybd_event(VK_CTRL, 0, UP, 0)
    time.sleep(0.1)


# ─────────────────────────────────────────────
# Translation Engines
# ─────────────────────────────────────────────

def translate_deepl(text: str, cfg: dict) -> tuple:
    if not cfg.get("api_key"):
        raise ValueError("DeepL API key is not set.")

    base = "https://api.deepl.com" if cfg.get("api_type") == "pro" else "https://api-free.deepl.com"
    url = f"{base}/v2/translate"
    body = {"text": [text], "target_lang": cfg["target_lang"]}
    if cfg["source_lang"] != "auto":
        body["source_lang"] = cfg["source_lang"]

    log.info(f"DeepL POST: {url}, target={cfg['target_lang']}, len={len(text)}")
    r = requests.post(url, headers={
        "Authorization": f"DeepL-Auth-Key {cfg['api_key']}",
        "Content-Type": "application/json",
    }, json=body, timeout=10)
    log.info(f"DeepL response: status={r.status_code}")

    if r.status_code == 403:
        raise ValueError("Invalid DeepL API key.")
    if r.status_code == 456:
        raise ValueError("DeepL quota exceeded.")
    r.raise_for_status()

    t = r.json()["translations"][0]
    result = t["text"]
    detected = t.get("detected_source_language", "?")
    log.info(f"DeepL result: {len(result)} chars, detected={detected}")
    return result, detected


def translate_google(text: str, cfg: dict) -> tuple:
    """Google Translate - free endpoint (no API key needed)."""
    src = to_google_code(cfg["source_lang"])
    tgt = to_google_code(cfg["target_lang"])

    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": text},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    translated = "".join(seg[0] for seg in data[0] if seg[0])
    detected = data[2] if isinstance(data[2], str) else src
    return translated, detected.upper()


# Language name map for Gemini prompts
LANG_NAMES = {
    "auto": "auto-detect", "BG": "Bulgarian", "CS": "Czech", "DA": "Danish",
    "DE": "German", "EL": "Greek", "EN": "English", "EN-US": "English",
    "EN-GB": "English", "ES": "Spanish", "ET": "Estonian", "FI": "Finnish",
    "FR": "French", "HU": "Hungarian", "ID": "Indonesian", "IT": "Italian",
    "JA": "Japanese", "KO": "Korean", "LT": "Lithuanian", "LV": "Latvian",
    "NB": "Norwegian", "NL": "Dutch", "PL": "Polish", "PT-BR": "Portuguese",
    "PT-PT": "Portuguese", "RO": "Romanian", "RU": "Russian", "SK": "Slovak",
    "SL": "Slovenian", "SV": "Swedish", "TR": "Turkish", "UK": "Ukrainian",
    "ZH": "Chinese", "ZH-HANS": "Simplified Chinese", "ZH-HANT": "Traditional Chinese",
    "AR": "Arabic", "HI": "Hindi", "TH": "Thai", "VI": "Vietnamese",
}


def translate_gemini(text: str, cfg: dict) -> tuple:
    """Translate using Google Gemini API via REST (no SDK needed)."""
    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        raise ValueError("Gemini API key is not set.")

    model = cfg.get("gemini_model", "gemini-2.5-flash")
    tgt_name = LANG_NAMES.get(cfg["target_lang"], cfg["target_lang"])

    if cfg["source_lang"] == "auto":
        src_instruction = "Detect the source language automatically."
    else:
        src_name = LANG_NAMES.get(cfg["source_lang"], cfg["source_lang"])
        src_instruction = f"The source language is {src_name}."

    prompt = (
        f"You are a professional translator. Translate the following text into {tgt_name}. "
        f"{src_instruction} "
        "Return ONLY the translated text, nothing else. No explanations, no quotes, no markdown.\n\n"
        f"{text}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    log.info(f"Gemini POST: model={model}, target={tgt_name}, len={len(text)}")
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        },
    }, timeout=15)
    log.info(f"Gemini response: status={r.status_code}")

    if r.status_code == 400:
        err = r.json().get("error", {}).get("message", "Bad request")
        raise ValueError(f"Gemini error: {err}")
    if r.status_code == 403:
        raise ValueError("Invalid Gemini API key.")
    if r.status_code == 429:
        raise ValueError("Gemini rate limit exceeded. Try again later.")
    r.raise_for_status()

    data = r.json()
    try:
        translated = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        log.error(f"Gemini unexpected response: {data}")
        raise ValueError(f"Gemini returned unexpected format: {e}")

    # Try to detect source language from context (Gemini doesn't return it explicitly)
    detected = "?" if cfg["source_lang"] == "auto" else cfg["source_lang"]
    log.info(f"Gemini result: {len(translated)} chars")
    return translated, detected


def translate_text(text: str, cfg: dict) -> tuple:
    engine = cfg.get("engine", "deepl")
    log.info(f"Translating via {engine}: {len(text)} chars -> {cfg['target_lang']}")
    if engine == "google":
        return translate_google(text, cfg)
    if engine == "gemini":
        return translate_gemini(text, cfg)
    return translate_deepl(text, cfg)


def get_deepl_usage(cfg: dict) -> dict:
    """
    Query DeepL /v2/usage endpoint.
    Returns {"character_count": int, "character_limit": int} or None on error.
    """
    if not cfg.get("api_key"):
        return None
    try:
        base = "https://api.deepl.com" if cfg.get("api_type") == "pro" else "https://api-free.deepl.com"
        r = requests.get(f"{base}/v2/usage", headers={
            "Authorization": f"DeepL-Auth-Key {cfg['api_key']}",
        }, timeout=5)
        if r.status_code == 200:
            data = r.json()
            log.info(f"DeepL usage: {data.get('character_count')}/{data.get('character_limit')}")
            return data
    except Exception as e:
        log.error(f"DeepL usage query error: {e}")
    return None


def format_usage(count: int, limit: int) -> str:
    """Format usage numbers with comma separators."""
    pct = (count / limit * 100) if limit > 0 else 0
    return f"{count:,} / {limit:,}  ({pct:.1f}%)"


# ─────────────────────────────────────────────
# Themed Widget Helpers
# ─────────────────────────────────────────────

class ThemedMixin:
    """Helpers to apply theme colors to tkinter widgets."""

    def apply_theme(self, widget, t: dict, role="bg"):
        """Apply theme to a basic tk widget."""
        if role == "bg":
            widget.configure(bg=t["bg"])
        elif role == "card":
            widget.configure(bg=t["card_bg"])
        elif role == "input":
            widget.configure(bg=t["input_bg"], fg=t["fg"],
                             insertbackground=t["fg"],
                             highlightbackground=t["border"],
                             highlightcolor=t["border_focus"])

    def make_label(self, parent, text, t, size=10, bold=False, color=None):
        weight = "bold" if bold else "normal"
        lbl = tk.Label(parent, text=text, bg=parent.cget("bg"),
                       fg=color or t["fg"],
                       font=("Segoe UI", size, weight))
        return lbl

    def make_entry(self, parent, t, var=None, show="", width=40):
        e = tk.Entry(parent, textvariable=var, show=show, width=width,
                     font=("Segoe UI", 10),
                     bg=t["input_bg"], fg=t["fg"],
                     insertbackground=t["fg"],
                     relief=tk.FLAT,
                     highlightthickness=1,
                     highlightbackground=t["border"],
                     highlightcolor=t["border_focus"])
        return e

    def make_button(self, parent, text, t, command, primary=True):
        bg = t["btn_bg"] if primary else t["btn_secondary_bg"]
        fg = t["btn_fg"] if primary else t["btn_secondary_fg"]
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                        font=("Segoe UI", 10),
                        relief=tk.FLAT, cursor="hand2",
                        padx=16, pady=6, borderwidth=0)
        hover_bg = t["accent_hover"] if primary else t["border"]
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def make_section(self, parent, title, t):
        """Create a titled card-like section frame."""
        outer = tk.Frame(parent, bg=t["card_bg"], highlightthickness=1,
                         highlightbackground=t["border"], padx=16, pady=12)
        if title:
            lbl = tk.Label(outer, text=title, bg=t["card_bg"], fg=t["accent"],
                           font=("Segoe UI", 10, "bold"), anchor="w")
            lbl.pack(fill=tk.X, pady=(0, 8))
        return outer


# ─────────────────────────────────────────────
# Translation Popup
# ─────────────────────────────────────────────

class TranslationPopup(ThemedMixin):
    def __init__(self, master):
        self.master = master
        self.win = None
        self._txt_orig = None
        self._txt_trans = None
        self._status_label = None
        self._copy_btn = None
        self._translated_text = ""
        self._usage_frame = None
        self._usage_label = None
        self._usage_pct_label = None
        self._usage_canvas = None
        self._theme = None
        self._engine = None

    def show_loading(self, original: str, mouse_x: int, mouse_y: int, t: dict, engine: str):
        """Show popup immediately with original text and a loading indicator."""
        self._theme = t  # Set theme FIRST before anything else
        self._engine = engine
        self._close()

        win = tk.Toplevel(self.master)
        self.win = win
        win.overrideredirect(True)  # borderless
        win.attributes("-topmost", True)
        win.configure(bg=t["bg"])

        # Position
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = mouse_x + POPUP_OFFSET_X
        y = mouse_y + POPUP_OFFSET_Y
        if x + POPUP_DEFAULT_W > sw:
            x = mouse_x - POPUP_DEFAULT_W - POPUP_OFFSET_X
        if y + POPUP_DEFAULT_H > sh:
            y = sh - POPUP_DEFAULT_H - 20
        if y < 0:
            y = 10
        win.geometry(f"{POPUP_DEFAULT_W}x{POPUP_DEFAULT_H}+{x}+{y}")

        # ── Title bar ──
        title_bar = tk.Frame(win, bg=t["bg_secondary"], height=36)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        title_icon = tk.Label(title_bar, text="Q", bg=t["accent"], fg="#ffffff",
                              font=("Segoe UI", 10, "bold"), padx=8, pady=2)
        title_icon.pack(side=tk.LEFT, padx=(8, 6), pady=4)

        engine_label = engine.capitalize()
        self._status_label = tk.Label(title_bar, text=f"  Translating via {engine_label}...",
                                      bg=t["bg_secondary"], fg=t["fg_secondary"],
                                      font=("Segoe UI", 9))
        self._status_label.pack(side=tk.LEFT, padx=4, pady=4)

        close_btn = tk.Label(title_bar, text=" \u2715 ", bg=t["bg_secondary"], fg=t["fg_secondary"],
                             font=("Segoe UI", 11), cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        close_btn.bind("<Button-1>", lambda e: self._close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=t["error"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=t["fg_secondary"]))

        # Draggable title bar
        self._drag_data = {"x": 0, "y": 0}
        title_bar.bind("<Button-1>", self._drag_start)
        title_bar.bind("<B1-Motion>", self._drag_move)

        # ── Content ──
        body = tk.Frame(win, bg=t["bg"], padx=12, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        # Headers
        hdr = tk.Frame(body, bg=t["bg"])
        hdr.pack(fill=tk.X, pady=(0, 6))
        tk.Label(hdr, text="Original", bg=t["bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, expand=True, anchor="w")
        tk.Label(hdr, text="Translation", bg=t["bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT, expand=True, anchor="e")

        # Text panels
        panels = tk.Frame(body, bg=t["bg"])
        panels.pack(fill=tk.BOTH, expand=True)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=0)
        panels.columnconfigure(2, weight=1)
        panels.rowconfigure(0, weight=1)

        # Original
        orig_frame = tk.Frame(panels, bg=t["card_bg"], highlightthickness=1,
                              highlightbackground=t["border"])
        orig_frame.grid(row=0, column=0, sticky="nsew")
        self._txt_orig = tk.Text(orig_frame, wrap=tk.WORD, font=("Segoe UI", 11),
                                 bg=t["card_bg"], fg=t["fg"], relief=tk.FLAT,
                                 padx=10, pady=8, borderwidth=0, highlightthickness=0,
                                 cursor="arrow", selectbackground=t["accent"])
        self._txt_orig.insert("1.0", original)
        self._txt_orig.config(state=tk.DISABLED)
        self._txt_orig.pack(fill=tk.BOTH, expand=True)
        self._setup_context_menu(self._txt_orig, t, is_translation=False)

        # Separator
        sep = tk.Frame(panels, bg=t["bg"], width=8)
        sep.grid(row=0, column=1, sticky="ns")

        # Translation (loading state)
        trans_frame = tk.Frame(panels, bg=t["card_bg_alt"], highlightthickness=1,
                               highlightbackground=t["border"])
        trans_frame.grid(row=0, column=2, sticky="nsew")
        self._txt_trans = tk.Text(trans_frame, wrap=tk.WORD, font=("Segoe UI", 11),
                                  bg=t["card_bg_alt"], fg=t["fg_dim"], relief=tk.FLAT,
                                  padx=10, pady=8, borderwidth=0, highlightthickness=0,
                                  cursor="arrow", selectbackground=t["accent"])
        self._txt_trans.insert("1.0", "Translating...")
        self._txt_trans.config(state=tk.DISABLED)
        self._txt_trans.pack(fill=tk.BOTH, expand=True)
        self._setup_context_menu(self._txt_trans, t, is_translation=True)

        # ── Resize grip (bottom-right corner indicator) ──
        grip = tk.Label(win, text="\u25E2", bg=t["bg"], fg=t["fg_dim"],
                        font=("Segoe UI", 8), cursor="bottom_right_corner", anchor="se")
        grip.place(relx=1.0, rely=1.0, anchor="se")

        # Setup edge/corner resize on the whole window
        self._setup_resize(win)

        # ── Usage bar (DeepL only, hidden initially) ──
        self._usage_frame = tk.Frame(win, bg=t["bg"], padx=12)
        # Don't pack yet — will be shown when usage data arrives

        usage_inner = tk.Frame(self._usage_frame, bg=t["bg"])
        usage_inner.pack(fill=tk.X)

        self._usage_label = tk.Label(usage_inner, text="", bg=t["bg"],
                                     fg=t["fg_dim"], font=("Segoe UI", 8), anchor="w")
        self._usage_label.pack(side=tk.LEFT)

        self._usage_pct_label = tk.Label(usage_inner, text="", bg=t["bg"],
                                         fg=t["fg_dim"], font=("Segoe UI", 8), anchor="e")
        self._usage_pct_label.pack(side=tk.RIGHT)

        # Progress bar canvas
        self._usage_canvas = tk.Canvas(self._usage_frame, height=6, bg=t["border"],
                                       highlightthickness=0, bd=0)
        self._usage_canvas.pack(fill=tk.X, pady=(3, 0))

        # ── Bottom bar ──
        bbar = tk.Frame(win, bg=t["bg"], padx=12, pady=8)
        bbar.pack(fill=tk.X)

        self._copy_btn = self.make_button(bbar, "Copy Translation", t,
                                          command=self._copy, primary=True)
        self._copy_btn.pack(side=tk.LEFT)
        self._copy_btn.config(state=tk.DISABLED)

        esc_btn = self.make_button(bbar, "Close  Esc", t,
                                   command=self._close, primary=False)
        esc_btn.pack(side=tk.RIGHT)

        win.bind("<Escape>", lambda e: self._close())
        win.after(50, win.focus_force)

    def fill_translation(self, translated: str, src_lang: str, tgt_lang: str):
        """Called when translation is ready — fill in the result."""
        log.info(f"fill_translation called: {len(translated)} chars, win exists={self.win and self.win.winfo_exists()}")
        if not self.win or not self.win.winfo_exists():
            log.warning("fill_translation: window gone, skip")
            return
        if not self._theme:
            log.error("fill_translation: _theme not set!")
            return
        try:
            t = self._theme
            self._translated_text = translated

            self._txt_trans.config(state=tk.NORMAL)
            self._txt_trans.delete("1.0", tk.END)
            self._txt_trans.insert("1.0", translated)
            self._txt_trans.config(state=tk.DISABLED, fg=t["fg"])

            if self._status_label:
                self._status_label.config(text=f"  {src_lang} \u2192 {tgt_lang}")

            if self._copy_btn:
                self._copy_btn.config(state=tk.NORMAL)
            log.info("fill_translation: done")
        except Exception as e:
            log.error(f"fill_translation error: {e}\n{traceback.format_exc()}")

    def show_error(self, msg: str):
        if not self.win or not self.win.winfo_exists():
            return
        t = self._theme
        self._txt_trans.config(state=tk.NORMAL)
        self._txt_trans.delete("1.0", tk.END)
        self._txt_trans.insert("1.0", f"Error: {msg}")
        self._txt_trans.config(state=tk.DISABLED, fg=t["error"])
        if self._status_label:
            self._status_label.config(text="  Translation failed", fg=t["error"])

    def show_usage(self, usage_data: dict):
        """Show DeepL usage bar at bottom of popup."""
        if not self.win or not self.win.winfo_exists():
            return
        if not usage_data or not self._usage_frame or not self._theme:
            return
        try:
            t = self._theme
            count = usage_data.get("character_count", 0)
            limit = usage_data.get("character_limit", 1)
            pct = count / limit if limit > 0 else 0

            # Show the usage frame
            self._usage_frame.pack(fill=tk.X, pady=(4, 0))

            self._usage_label.config(text=f"DeepL:  {count:,} / {limit:,}")

            pct_text = f"{pct * 100:.1f}%"
            if pct > 0.9:
                self._usage_pct_label.config(text=pct_text, fg=t["error"])
            elif pct > 0.7:
                self._usage_pct_label.config(text=pct_text, fg="#ff9500")
            else:
                self._usage_pct_label.config(text=pct_text, fg=t["success"])

            # Draw progress bar
            self.win.update_idletasks()
            w = self._usage_canvas.winfo_width()
            if w < 10:
                w = 400
            h = 6
            self._usage_canvas.delete("all")
            self._usage_canvas.create_rectangle(0, 0, w, h, fill=t["border"], outline="")
            fill_w = int(w * pct)
            if pct > 0.9:
                bar_color = t["error"]
            elif pct > 0.7:
                bar_color = "#ff9500"
            else:
                bar_color = t["accent"]
            if fill_w > 0:
                self._usage_canvas.create_rectangle(0, 0, fill_w, h, fill=bar_color, outline="")
        except Exception as e:
            log.error(f"show_usage error: {e}")

    def _copy(self):
        if self._translated_text and self.win:
            self.win.clipboard_clear()
            self.win.clipboard_append(self._translated_text)
            self._copy_btn.config(text="\u2713 Copied!")
            self.win.after(1200, lambda: self._safe_reset_btn())

    def _safe_reset_btn(self):
        try:
            if self._copy_btn and self.win and self.win.winfo_exists():
                self._copy_btn.config(text="Copy Translation")
        except Exception:
            pass

    def _close(self):
        try:
            if self.win and self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass
        self.win = None

    # ── Drag (title bar) ──

    def _drag_start(self, e):
        self._drag_data["x"] = e.x
        self._drag_data["y"] = e.y

    def _drag_move(self, e):
        if self.win:
            dx = e.x - self._drag_data["x"]
            dy = e.y - self._drag_data["y"]
            x = self.win.winfo_x() + dx
            y = self.win.winfo_y() + dy
            self.win.geometry(f"+{x}+{y}")

    # ── Resize (edges & corners) ──

    EDGE_SIZE = 8  # pixels from edge to detect resize

    def _setup_resize(self, win):
        """Bind resize events on the window AND all child widgets."""
        self._resize_data = {"edge": None, "sx": 0, "sy": 0, "sw": 0, "sh": 0, "wx": 0, "wy": 0}
        self._bind_resize_recursive(win)

    def _bind_resize_recursive(self, widget):
        """Recursively bind resize events to widget and all descendants."""
        widget.bind("<Motion>", self._resize_cursor, add="+")
        widget.bind("<Button-1>", self._resize_start, add="+")
        widget.bind("<B1-Motion>", self._resize_move, add="+")
        widget.bind("<ButtonRelease-1>", self._resize_end, add="+")
        for child in widget.winfo_children():
            self._bind_resize_recursive(child)

    def _get_edge_from_root(self, e):
        """Detect edge using screen-absolute coordinates (works regardless of which widget got the event)."""
        if not self.win:
            return None
        # Convert to window-relative coordinates
        win_x = self.win.winfo_rootx()
        win_y = self.win.winfo_rooty()
        win_w = self.win.winfo_width()
        win_h = self.win.winfo_height()

        x = e.x_root - win_x  # relative to window left
        y = e.y_root - win_y  # relative to window top
        sz = self.EDGE_SIZE

        on_left = x < sz
        on_right = x > win_w - sz
        on_top = y < sz
        on_bottom = y > win_h - sz

        if on_bottom and on_right:
            return "se"
        if on_bottom and on_left:
            return "sw"
        if on_top and on_right:
            return "ne"
        if on_top and on_left:
            return "nw"
        if on_bottom:
            return "s"
        if on_right:
            return "e"
        if on_left:
            return "w"
        if on_top:
            return "n"
        return None

    CURSOR_MAP = {
        "n": "top_side", "s": "bottom_side", "e": "right_side", "w": "left_side",
        "ne": "top_right_corner", "nw": "top_left_corner",
        "se": "bottom_right_corner", "sw": "bottom_left_corner",
    }

    def _resize_cursor(self, e):
        if not self.win:
            return
        edge = self._get_edge_from_root(e)
        cursor = self.CURSOR_MAP.get(edge, "")
        try:
            e.widget.config(cursor=cursor)
        except Exception:
            pass

    def _resize_start(self, e):
        edge = self._get_edge_from_root(e)
        if not edge or not self.win:
            return
        self._resize_data = {
            "edge": edge,
            "sx": e.x_root, "sy": e.y_root,
            "sw": self.win.winfo_width(), "sh": self.win.winfo_height(),
            "wx": self.win.winfo_x(), "wy": self.win.winfo_y(),
        }

    def _resize_move(self, e):
        d = self._resize_data
        edge = d.get("edge")
        if not edge or not self.win:
            return

        dx = e.x_root - d["sx"]
        dy = e.y_root - d["sy"]
        x, y, w, h = d["wx"], d["wy"], d["sw"], d["sh"]

        if "e" in edge:
            w = max(POPUP_MIN_W, d["sw"] + dx)
        if "s" in edge:
            h = max(POPUP_MIN_H, d["sh"] + dy)
        if "w" in edge:
            nw = max(POPUP_MIN_W, d["sw"] - dx)
            x = d["wx"] + (d["sw"] - nw)
            w = nw
        if "n" in edge:
            nh = max(POPUP_MIN_H, d["sh"] - dy)
            y = d["wy"] + (d["sh"] - nh)
            h = nh

        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _resize_end(self, e):
        self._resize_data["edge"] = None

    # ── Right-click context menu ──

    def _setup_context_menu(self, text_widget, t, is_translation=False):
        """Add right-click context menu to a Text widget."""
        menu = tk.Menu(text_widget, tearoff=0,
                       bg=t["card_bg"], fg=t["fg"],
                       activebackground=t["accent"], activeforeground="#ffffff",
                       font=("Segoe UI", 10), borderwidth=1, relief=tk.FLAT)

        def copy_all():
            text_widget.config(state=tk.NORMAL)
            content = text_widget.get("1.0", tk.END).strip()
            text_widget.config(state=tk.DISABLED)
            if content and self.win:
                self.win.clipboard_clear()
                self.win.clipboard_append(content)

        def copy_selection():
            try:
                text_widget.config(state=tk.NORMAL)
                sel = text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                text_widget.config(state=tk.DISABLED)
                if sel and self.win:
                    self.win.clipboard_clear()
                    self.win.clipboard_append(sel)
            except tk.TclError:
                pass  # no selection

        def select_all():
            text_widget.config(state=tk.NORMAL)
            text_widget.tag_add(tk.SEL, "1.0", tk.END)
            text_widget.config(state=tk.DISABLED)

        menu.add_command(label="Copy All", command=copy_all)
        menu.add_command(label="Copy Selection", command=copy_selection)
        menu.add_separator()
        menu.add_command(label="Select All", command=select_all)

        def show_menu(event):
            # Enable text selection by temporarily making it normal
            text_widget.config(state=tk.NORMAL, cursor="xterm")
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                text_widget.config(state=tk.DISABLED)

        text_widget.bind("<Button-3>", show_menu)

        # Allow mouse selection in disabled text widget
        def enable_select(event):
            text_widget.config(state=tk.NORMAL, cursor="xterm")
        def disable_select(event):
            text_widget.config(state=tk.DISABLED, cursor="arrow")

        text_widget.bind("<Button-1>", enable_select, add="+")
        text_widget.bind("<ButtonRelease-1>", lambda e: text_widget.after(50, lambda: disable_select(e)), add="+")


# ─────────────────────────────────────────────
# Settings Window
# ─────────────────────────────────────────────

class SettingsWindow(ThemedMixin):
    def __init__(self, master, cfg, on_save):
        self.master = master
        self.cfg = cfg
        self.on_save = on_save
        self.win = None

    def show(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return

        t = get_theme(self.cfg.get("theme", "system"))
        win = tk.Toplevel(self.master)
        self.win = win
        win.title(f"{APP_NAME} Settings")
        win.configure(bg=t["bg"])
        win.attributes("-topmost", True)
        win.resizable(False, False)

        # Main container with padding
        main = tk.Frame(win, bg=t["bg"], padx=24, pady=20)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Header ──
        hdr = tk.Frame(main, bg=t["bg"])
        hdr.pack(fill=tk.X, pady=(0, 16))
        tk.Label(hdr, text="Q", bg=t["accent"], fg="#ffffff",
                 font=("Segoe UI", 14, "bold"), padx=10, pady=2).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(hdr, text=f"{APP_NAME} Settings",
                 bg=t["bg"], fg=t["fg"],
                 font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text=f"v{APP_VERSION}",
                 bg=t["bg"], fg=t["fg_dim"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=8, pady=(4, 0))

        # ── Scrollable content area via Canvas ──
        content = tk.Frame(main, bg=t["bg"])
        content.pack(fill=tk.BOTH, expand=True)

        # ════════ Translation Engine ════════
        sec = self.make_section(content, "Translation Engine", t)
        sec.pack(fill=tk.X, pady=(0, 10))

        engine_var = tk.StringVar(value=self.cfg.get("engine", "deepl"))
        eng_frame = tk.Frame(sec, bg=t["card_bg"])
        eng_frame.pack(fill=tk.X, pady=(0, 8))

        for val, label in [("deepl", "DeepL"), ("google", "Google Translate (Free)"), ("gemini", "Gemini AI")]:
            rb = tk.Radiobutton(eng_frame, text=label, variable=engine_var, value=val,
                                bg=t["card_bg"], fg=t["fg"], selectcolor=t["input_bg"],
                                activebackground=t["card_bg"], activeforeground=t["fg"],
                                font=("Segoe UI", 10), cursor="hand2")
            rb.pack(side=tk.LEFT, padx=(0, 16))

        # DeepL API config (show/hide based on engine)
        deepl_frame = tk.Frame(sec, bg=t["card_bg"])

        tk.Label(deepl_frame, text="API Key", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
        api_var = tk.StringVar(value=self.cfg.get("api_key", ""))
        api_entry = self.make_entry(deepl_frame, t, var=api_var, show="\u2022", width=50)
        api_entry.pack(fill=tk.X, pady=(0, 6))

        show_var = tk.BooleanVar(value=False)
        show_cb = tk.Checkbutton(deepl_frame, text="Show key", variable=show_var,
                                 bg=t["card_bg"], fg=t["fg_secondary"],
                                 selectcolor=t["input_bg"], activebackground=t["card_bg"],
                                 font=("Segoe UI", 9), cursor="hand2",
                                 command=lambda: api_entry.config(show="" if show_var.get() else "\u2022"))
        show_cb.pack(anchor="w", pady=(0, 6))

        api_type_var = tk.StringVar(value=self.cfg.get("api_type", "free"))
        atf = tk.Frame(deepl_frame, bg=t["card_bg"])
        atf.pack(fill=tk.X, pady=(0, 4))
        tk.Label(atf, text="Plan:", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        for val, label in [("free", "Free"), ("pro", "Pro")]:
            tk.Radiobutton(atf, text=label, variable=api_type_var, value=val,
                           bg=t["card_bg"], fg=t["fg"], selectcolor=t["input_bg"],
                           activebackground=t["card_bg"], activeforeground=t["fg"],
                           font=("Segoe UI", 9), cursor="hand2").pack(side=tk.LEFT, padx=(0, 12))

        # ── DeepL Usage Display ──
        usage_frame = tk.Frame(deepl_frame, bg=t["card_bg"])
        usage_frame.pack(fill=tk.X, pady=(8, 0))

        usage_sep = tk.Frame(usage_frame, bg=t["separator"], height=1)
        usage_sep.pack(fill=tk.X, pady=(0, 8))

        usage_row = tk.Frame(usage_frame, bg=t["card_bg"])
        usage_row.pack(fill=tk.X)

        usage_info_label = tk.Label(usage_row, text="API Usage:  Click 'Check' to load",
                                    bg=t["card_bg"], fg=t["fg_dim"],
                                    font=("Segoe UI", 9), anchor="w")
        usage_info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        usage_bar_canvas = tk.Canvas(usage_frame, height=8, bg=t["border"],
                                     highlightthickness=0, bd=0)

        def check_usage():
            key = api_var.get().strip()
            atype = api_type_var.get()
            if not key:
                usage_info_label.config(text="API Usage:  Enter API key first", fg=t["error"])
                return
            usage_info_label.config(text="API Usage:  Checking...", fg=t["fg_dim"])
            check_btn.config(state=tk.DISABLED)
            win.update_idletasks()

            def do_check():
                tmp_cfg = {"api_key": key, "api_type": atype}
                data = get_deepl_usage(tmp_cfg)
                def update_ui():
                    check_btn.config(state=tk.NORMAL)
                    if data:
                        count = data.get("character_count", 0)
                        limit = data.get("character_limit", 1)
                        pct = count / limit if limit > 0 else 0
                        usage_info_label.config(
                            text=f"API Usage:  {count:,} / {limit:,}  ({pct * 100:.1f}%)",
                            fg=t["fg"])
                        # Show and draw bar
                        usage_bar_canvas.pack(fill=tk.X, pady=(4, 0))
                        win.update_idletasks()
                        w = usage_bar_canvas.winfo_width()
                        if w < 10:
                            w = 300
                        usage_bar_canvas.delete("all")
                        usage_bar_canvas.create_rectangle(0, 0, w, 8, fill=t["border"], outline="")
                        fill_w = int(w * pct)
                        if pct > 0.9:
                            bar_c = t["error"]
                        elif pct > 0.7:
                            bar_c = "#ff9500"
                        else:
                            bar_c = t["accent"]
                        if fill_w > 0:
                            usage_bar_canvas.create_rectangle(0, 0, fill_w, 8, fill=bar_c, outline="")
                        # Resize window
                        win.update_idletasks()
                        win.geometry("")
                    else:
                        usage_info_label.config(text="API Usage:  Failed to fetch (check key)", fg=t["error"])
                win.after(0, update_ui)

            threading.Thread(target=do_check, daemon=True).start()

        check_btn = self.make_button(usage_row, "Check", t, check_usage, primary=False)
        check_btn.pack(side=tk.RIGHT)

        # ── Gemini config (show/hide based on engine) ──
        gemini_frame = tk.Frame(sec, bg=t["card_bg"])

        tk.Label(gemini_frame, text="Gemini API Key", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
        gemini_key_var = tk.StringVar(value=self.cfg.get("gemini_api_key", ""))
        gemini_entry = self.make_entry(gemini_frame, t, var=gemini_key_var, show="\u2022", width=50)
        gemini_entry.pack(fill=tk.X, pady=(0, 6))

        gemini_show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(gemini_frame, text="Show key", variable=gemini_show_var,
                       bg=t["card_bg"], fg=t["fg_secondary"],
                       selectcolor=t["input_bg"], activebackground=t["card_bg"],
                       font=("Segoe UI", 9), cursor="hand2",
                       command=lambda: gemini_entry.config(show="" if gemini_show_var.get() else "\u2022")
                       ).pack(anchor="w", pady=(0, 6))

        gmf = tk.Frame(gemini_frame, bg=t["card_bg"])
        gmf.pack(fill=tk.X, pady=(0, 4))
        tk.Label(gmf, text="Model:", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        gemini_model_var = tk.StringVar(value=self.cfg.get("gemini_model", "gemini-2.5-flash"))
        gemini_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
        gm_combo = ttk.Combobox(gmf, textvariable=gemini_model_var, values=gemini_models,
                                state="readonly", width=24)
        gm_combo.pack(side=tk.LEFT)

        gemini_note = tk.Label(gemini_frame, bg=t["card_bg"], fg=t["fg_dim"],
                               font=("Segoe UI", 8), anchor="w",
                               text="Free: no credit card needed. Get key at aistudio.google.com")
        gemini_note.pack(fill=tk.X, pady=(4, 0))

        def toggle_engine(*_args):
            deepl_frame.pack_forget()
            gemini_frame.pack_forget()
            eng = engine_var.get()
            if eng == "deepl":
                deepl_frame.pack(fill=tk.X, pady=(4, 0))
            elif eng == "gemini":
                gemini_frame.pack(fill=tk.X, pady=(4, 0))
            # Resize window
            win.update_idletasks()
            win.geometry("")

        engine_var.trace_add("write", toggle_engine)
        toggle_engine()

        # ════════ Language ════════
        sec2 = self.make_section(content, "Language", t)
        sec2.pack(fill=tk.X, pady=(0, 10))

        lang_grid = tk.Frame(sec2, bg=t["card_bg"])
        lang_grid.pack(fill=tk.X)
        lang_grid.columnconfigure(0, weight=1)
        lang_grid.columnconfigure(1, weight=0, minsize=16)
        lang_grid.columnconfigure(2, weight=1)

        # Source
        tk.Label(lang_grid, text="Source", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=(0, 2))
        src_codes = list(LANGUAGES_SOURCE.keys())
        src_labels = [f"{LANGUAGES_SOURCE[c]}  ({c})" if c != "auto" else "Auto Detect" for c in src_codes]
        src_combo = ttk.Combobox(lang_grid, values=src_labels, state="readonly", width=28)
        try:
            src_combo.current(src_codes.index(self.cfg.get("source_lang", "auto")))
        except ValueError:
            src_combo.current(0)
        src_combo.grid(row=1, column=0, sticky="ew", pady=(0, 4))

        # Arrow
        tk.Label(lang_grid, text="\u2192", bg=t["card_bg"], fg=t["accent"],
                 font=("Segoe UI", 16)).grid(row=1, column=1, padx=8)

        # Target
        tk.Label(lang_grid, text="Target", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", pady=(0, 2))
        tgt_codes = list(LANGUAGES_TARGET.keys())
        tgt_labels = [f"{LANGUAGES_TARGET[c]}  ({c})" for c in tgt_codes]
        tgt_combo = ttk.Combobox(lang_grid, values=tgt_labels, state="readonly", width=28)
        try:
            tgt_combo.current(tgt_codes.index(self.cfg.get("target_lang", "KO")))
        except ValueError:
            tgt_combo.current(0)
        tgt_combo.grid(row=1, column=2, sticky="ew", pady=(0, 4))

        # ════════ Hotkey ════════
        sec3 = self.make_section(content, "Hotkey", t)
        sec3.pack(fill=tk.X, pady=(0, 10))

        hk_names = list(HOTKEY_PRESETS.keys())
        hk_labels = [f"{n}   \u2014  {HOTKEY_PRESETS[n]['desc']}" for n in hk_names]
        hk_combo = ttk.Combobox(sec3, values=hk_labels, state="readonly", width=48)
        current_hk = self.cfg.get("hotkey", "Ctrl+C, C")
        try:
            hk_combo.current(hk_names.index(current_hk))
        except ValueError:
            hk_combo.current(0)
        hk_combo.pack(fill=tk.X, pady=(0, 4))

        hk_note = tk.Label(sec3, text="", bg=t["card_bg"], fg=t["fg_dim"],
                           font=("Segoe UI", 8), anchor="w")
        hk_note.pack(fill=tk.X)

        def update_note(*_):
            p = HOTKEY_PRESETS[hk_names[hk_combo.current()]]
            if p["copies"]:
                hk_note.config(text="This hotkey includes copy — just select text and press it")
            else:
                hk_note.config(text="Copy text first (Ctrl+C), then press this hotkey")
        hk_combo.bind("<<ComboboxSelected>>", update_note)
        update_note()

        # ════════ Appearance & General ════════
        sec4 = self.make_section(content, "Appearance & General", t)
        sec4.pack(fill=tk.X, pady=(0, 10))

        row_f = tk.Frame(sec4, bg=t["card_bg"])
        row_f.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row_f, text="Theme:", bg=t["card_bg"], fg=t["fg_secondary"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        theme_var = tk.StringVar(value=self.cfg.get("theme", "system"))
        for val, label in [("system", "System"), ("light", "Light"), ("dark", "Dark")]:
            tk.Radiobutton(row_f, text=label, variable=theme_var, value=val,
                           bg=t["card_bg"], fg=t["fg"], selectcolor=t["input_bg"],
                           activebackground=t["card_bg"], activeforeground=t["fg"],
                           font=("Segoe UI", 10), cursor="hand2").pack(side=tk.LEFT, padx=(0, 12))

        autostart_var = tk.BooleanVar(value=self.cfg.get("autostart", True))
        tk.Checkbutton(sec4, text="Start with Windows", variable=autostart_var,
                       bg=t["card_bg"], fg=t["fg"], selectcolor=t["input_bg"],
                       activebackground=t["card_bg"],
                       font=("Segoe UI", 10), cursor="hand2").pack(anchor="w")

        # ════════ Buttons ════════
        btn_bar = tk.Frame(main, bg=t["bg"])
        btn_bar.pack(fill=tk.X, pady=(12, 0))

        def do_save():
            self.cfg["engine"] = engine_var.get()
            self.cfg["api_key"] = api_var.get().strip()
            self.cfg["api_type"] = api_type_var.get()
            self.cfg["gemini_api_key"] = gemini_key_var.get().strip()
            self.cfg["gemini_model"] = gemini_model_var.get()
            self.cfg["source_lang"] = src_codes[src_combo.current()]
            self.cfg["target_lang"] = tgt_codes[tgt_combo.current()]
            self.cfg["hotkey"] = hk_names[hk_combo.current()]
            self.cfg["theme"] = theme_var.get()
            self.cfg["autostart"] = autostart_var.get()
            self.on_save(self.cfg)
            win.destroy()

        self.make_button(btn_bar, "Save", t, do_save, primary=True).pack(side=tk.RIGHT, padx=(8, 0))
        self.make_button(btn_bar, "Cancel", t, win.destroy, primary=False).pack(side=tk.RIGHT)

        win.bind("<Escape>", lambda e: win.destroy())

        # Fit window to content
        win.update_idletasks()
        w = max(520, win.winfo_reqwidth())
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")


# ─────────────────────────────────────────────
# Hotkey Detector
# ─────────────────────────────────────────────

class HotkeyDetector:
    MODIFIER_MAP = {
        pynput_kb.Key.ctrl_l: "ctrl", pynput_kb.Key.ctrl_r: "ctrl",
        pynput_kb.Key.shift_l: "shift", pynput_kb.Key.shift_r: "shift",
        pynput_kb.Key.alt_l: "alt", pynput_kb.Key.alt_r: "alt",
    }

    def __init__(self, callback):
        self.callback = callback
        self.mods = set()
        self.idx = 0
        self.last_t = 0.0
        self.steps = []
        self.interval = 0.5
        self.listener = None
        self._lock = threading.Lock()

    def set_hotkey(self, name: str, interval=0.5):
        p = HOTKEY_PRESETS.get(name, HOTKEY_PRESETS["Ctrl+C, C"])
        with self._lock:
            self.steps = p["steps"]
            self.interval = interval
            self.idx = 0
            self.last_t = 0.0
        log.info(f"Hotkey: {name}")

    def start(self):
        self.listener = pynput_kb.Listener(on_press=self._press, on_release=self._release)
        self.listener.daemon = True
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()

    def _resolve(self, key) -> str:
        vk = getattr(key, "vk", None)
        if vk and 65 <= vk <= 90:
            return chr(vk).lower()
        if vk and 48 <= vk <= 57:
            return chr(vk)
        try:
            if key.char and ord(key.char) >= 32:
                return key.char.lower()
        except AttributeError:
            pass
        return ""

    def _press(self, key):
        try:
            m = self.MODIFIER_MAP.get(key)
            if m:
                self.mods.add(m)
                return
            ch = self._resolve(key)
            if not ch:
                return

            with self._lock:
                now = time.time()
                if self.idx > 0 and (now - self.last_t) > self.interval:
                    self.idx = 0

                if not self.steps:
                    return

                if self.idx >= len(self.steps):
                    self.idx = 0

                exp = self.steps[self.idx]
                if ch == exp["key"].lower() and set(exp["mod"]).issubset(self.mods):
                    self.idx += 1
                    self.last_t = now
                    if self.idx >= len(self.steps):
                        self.idx = 0
                        self.last_t = 0.0
                        threading.Thread(target=self._safe_cb, daemon=True).start()
                else:
                    first = self.steps[0]
                    if ch == first["key"].lower() and set(first["mod"]).issubset(self.mods):
                        self.idx = 1
                        self.last_t = now
                    else:
                        self.idx = 0
        except Exception as e:
            log.error(f"press err: {e}")

    def _release(self, key):
        m = self.MODIFIER_MAP.get(key)
        if m:
            self.mods.discard(m)

    def _safe_cb(self):
        try:
            self.callback()
        except Exception as e:
            log.error(f"cb err: {e}\n{traceback.format_exc()}")


# ─────────────────────────────────────────────
# Tray Icon
# ─────────────────────────────────────────────

def make_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill="#0071e3")
    try:
        f = ImageFont.truetype("segoeui.ttf", 34)
    except Exception:
        f = ImageFont.load_default()
    d.text((32, 30), "Q", fill="white", font=f, anchor="mm")
    return img


# ─────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────

class App:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.popup = TranslationPopup(self.root)
        self.hotkey = HotkeyDetector(callback=self._on_hotkey)
        self.tray = None
        log.info(f"{APP_NAME} v{APP_VERSION} init")

    def _get_clipboard(self) -> str:
        try:
            return self.root.clipboard_get().strip()
        except Exception:
            return ""

    def _on_hotkey(self):
        try:
            log.info("=== Hotkey triggered ===")
            mouse = get_mouse_pos()
            log.info(f"Mouse pos: {mouse}")

            preset = HOTKEY_PRESETS.get(self.cfg.get("hotkey", "Ctrl+C, C"), {})
            if not preset.get("copies", True):
                simulate_copy()
            time.sleep(0.08)

            text = self._get_clipboard()
            log.info(f"Clipboard: {len(text)} chars, first 50: {text[:50]!r}")
            if not text:
                log.info("Empty clipboard, skip")
                return

            engine = self.cfg.get("engine", "deepl")
            if engine == "deepl" and not self.cfg.get("api_key"):
                self.root.after(0, lambda: messagebox.showwarning(
                    APP_NAME, "DeepL API key not set.\nRight-click tray > Settings."))
                return
            if engine == "gemini" and not self.cfg.get("gemini_api_key"):
                self.root.after(0, lambda: messagebox.showwarning(
                    APP_NAME, "Gemini API key not set.\nRight-click tray > Settings."))
                return

            t = get_theme(self.cfg.get("theme", "system"))

            # Show popup immediately with loading state
            self.root.after(0, lambda: self.popup.show_loading(text, mouse[0], mouse[1], t, engine))

            # Small delay to let popup render before we block on API
            time.sleep(0.05)

            # Translate — capture all variables for lambda
            log.info(f"Calling translate_text via {engine}...")
            try:
                translated, detected = translate_text(text, self.cfg)
                log.info(f"Translation OK: {len(translated)} chars, detected={detected}")
            except Exception as te:
                log.error(f"translate_text FAILED: {te}\n{traceback.format_exc()}")
                err = str(te)
                self.root.after(0, lambda e=err: self.popup.show_error(e))
                return

            src = detected if self.cfg["source_lang"] == "auto" else self.cfg["source_lang"]
            tgt = self.cfg["target_lang"]

            # Use default arg to capture values (avoid late-binding lambda issues)
            self.root.after(0, lambda tr=translated, s=src, tg=tgt: self.popup.fill_translation(tr, s, tg))
            log.info("fill_translation scheduled")

            # Fetch DeepL usage after translation
            if engine == "deepl":
                try:
                    usage = get_deepl_usage(self.cfg)
                    if usage:
                        self.root.after(0, lambda u=usage: self.popup.show_usage(u))
                        log.info(f"Usage: {usage.get('character_count')}/{usage.get('character_limit')}")
                except Exception as ue:
                    log.error(f"Usage fetch error: {ue}")

        except Exception as e:
            log.error(f"hotkey err: {e}\n{traceback.format_exc()}")
            err = str(e)
            self.root.after(0, lambda msg=err: self.popup.show_error(msg))

    def _open_settings(self):
        def on_save(cfg):
            self.cfg = cfg
            save_config(cfg)
            set_autostart(cfg.get("autostart", False))
            self.hotkey.set_hotkey(cfg.get("hotkey", "Ctrl+C, C"), cfg.get("hotkey_interval", 0.5))
            self._rebuild_tray()

        sw = SettingsWindow(self.root, dict(self.cfg), on_save)
        self.root.after(0, sw.show)

    def _rebuild_tray(self):
        hk = self.cfg.get("hotkey", "Ctrl+C, C")
        eng = self.cfg.get("engine", "deepl").capitalize()
        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME} v{APP_VERSION}", None, enabled=False),
            pystray.MenuItem(f"Engine: {eng}  |  Hotkey: {hk}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", lambda: self.root.after(0, self._open_settings)),
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        if self.tray:
            self.tray.menu = menu
            self.tray.update_menu()

    def _quit(self):
        self.hotkey.stop()
        if self.tray:
            self.tray.stop()
        self.root.after(0, self.root.quit)

    def run(self):
        set_autostart(self.cfg.get("autostart", False))
        self.hotkey.set_hotkey(self.cfg.get("hotkey", "Ctrl+C, C"))
        self.hotkey.start()

        hk = self.cfg.get("hotkey", "Ctrl+C, C")
        eng = self.cfg.get("engine", "deepl").capitalize()
        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME} v{APP_VERSION}", None, enabled=False),
            pystray.MenuItem(f"Engine: {eng}  |  Hotkey: {hk}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", lambda: self.root.after(0, self._open_settings)),
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        self.tray = pystray.Icon(APP_NAME, make_icon(), APP_NAME, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

        needs_setup = (
            (self.cfg.get("engine") == "deepl" and not self.cfg.get("api_key")) or
            (self.cfg.get("engine") == "gemini" and not self.cfg.get("gemini_api_key"))
        )
        if needs_setup:
            self.root.after(500, self._open_settings)

        self.root.mainloop()


# ─────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────

if __name__ == "__main__":
    try:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "QuickLingo_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:
            ctypes.windll.user32.MessageBoxW(0, "Already running.", APP_NAME, 0x40)
            sys.exit(0)
        App().run()
    except Exception as e:
        log.critical(f"Fatal: {e}\n{traceback.format_exc()}")
        ctypes.windll.user32.MessageBoxW(0, f"Fatal error:\n{e}\n\nLog: {LOG_DIR/'debug.log'}", APP_NAME, 0x10)
        sys.exit(1)
