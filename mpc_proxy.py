# MPC Proxy – Kodi External Player Resume Overlay
# Final Version with:
# - MySQL / SQLite Resume
# - Portable Kodi UserData support
# - MPC-HC / MPC-BE autodetection
# - JSON-configurable UI
# - Automatic language detection from Kodi
# - Mouse + keyboard UI
# - Fully PyInstaller-safe (no unicode escape issues)

import os
import sys
import json
import subprocess
import pymysql
import sqlite3
import xml.etree.ElementTree as ET
import tkinter as tk

# =====================================================================
# Default Configuration
# =====================================================================
DEFAULT_PROXY_CONFIG = {
    "ui": {
        "min_resume_seconds": 120,
        "colors": {
            "background": "#000000",
            "text": "#FFFFFF",
            "button_normal": "#333333",
            "button_focus": "#1E90FF",
            "accent": "#1E90FF"
        },
        "font": {
            "title_size": 48,
            "button_size": 36
        }
    },
    "player": {
        "search_names": [
            "mpc-hc64.exe",
            "mpc-hc.exe",
            "mpc-be64.exe",
            "mpc-be.exe"
        ]
    },
    "userdata": {
        "userdata_path": None
    }
}

# =====================================================================
# Multi-language UI texts
# =====================================================================
LANG = {
    "en_gb": {
        "resume_question": "Resume from {time}?",
        "resume_button": "Resume at {time}",
        "restart": "Start from beginning"
    },
    "en_us": {
        "resume_question": "Resume from {time}?",
        "resume_button": "Resume at {time}",
        "restart": "Start from beginning"
    },
    "de_de": {
        "resume_question": "Fortsetzen ab {time}?",
        "resume_button": "Weiter bei {time}",
        "restart": "Von vorne starten"
    },
    "fr_fr": {
        "resume_question": "Reprendre à {time} ?",
        "resume_button": "Reprendre à {time}",
        "restart": "Recommencer depuis le début"
    },
    "es_es": {
        "resume_question": "Reanudar desde {time}?",
        "resume_button": "Reanudar en {time}",
        "restart": "Empezar desde el principio"
    },
    "it_it": {
        "resume_question": "Riprendere da {time}?",
        "resume_button": "Riprendi a {time}",
        "restart": "Ricomincia dall'inizio"
    },
    "pt_br": {
        "resume_question": "Retomar de {time}?",
        "resume_button": "Retomar em {time}",
        "restart": "Começar do início"
    },
    "pt_pt": {
        "resume_question": "Retomar desde {time}?",
        "resume_button": "Retomar em {time}",
        "restart": "Começar do início"
    },
    "nl_nl": {
        "resume_question": "Hervatten vanaf {time}?",
        "resume_button": "Hervatten op {time}",
        "restart": "Opnieuw starten"
    },
    "pl_pl": {
        "resume_question": "Wznawiać od {time}?",
        "resume_button": "Wznów o {time}",
        "restart": "Zacznij od początku"
    },
    "tr_tr": {
        "resume_question": "{time} konumundan devam edilsin mi?",
        "resume_button": "{time} konumundan devam et",
        "restart": "Baştan başla"
    }
}

# =====================================================================
# Merge dicts
# =====================================================================
def merge_dict(default, custom):
    if not isinstance(custom, dict):
        return default
    result = dict(default)
    for k, v in custom.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = v
    return result

# =====================================================================
# Load configuration file
# =====================================================================
def load_proxy_config(base_dir):
    path = os.path.join(base_dir, "mpc_proxy_config.json")
    if not os.path.exists(path):
        print("[WARN] No config found → using default")
        return DEFAULT_PROXY_CONFIG
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = merge_dict(DEFAULT_PROXY_CONFIG, user_cfg)
        print("[INFO] Config loaded")
        return cfg
    except Exception as e:
        print("[WARN] Failed to load config:", e)
        return DEFAULT_PROXY_CONFIG

# =====================================================================
# UserData path resolver (supports portable Kodi)
# =====================================================================
def get_userdata_path(proxy_cfg):
    user_cfg = proxy_cfg.get("userdata", {})
    custom = user_cfg.get("userdata_path", None)

    if custom:
        custom = os.path.abspath(custom)
        if os.path.exists(custom):
            print("[Kodi] Portable UserData path:", custom)
            return custom
        print("[WARN] Portable path does not exist:", custom)

    default = os.path.join(os.getenv("APPDATA"), "Kodi", "userdata")
    print("[Kodi] Default UserData path:", default)
    return default

# =====================================================================
# Get guisettings.xml from correct UserData path
# =====================================================================
def get_guisettings_path(proxy_cfg):
    ud = get_userdata_path(proxy_cfg)
    return os.path.join(ud, "guisettings.xml")

# =====================================================================
# Language detection
# =====================================================================
def get_kodi_language(proxy_cfg):
    path = get_guisettings_path(proxy_cfg)

    if not os.path.exists(path):
        print("[INFO] No guisettings.xml → en_gb")
        return "en_gb"

    try:
        tree = ET.parse(path)
        root = tree.getroot()

        # Kodi ≥ 20 (new layout)
        node = root.find('.//setting[@id="locale.language"]')
        if node is not None and node.text:
            c = node.text.lower().strip()
            if c.startswith("resource.language."):
                c = c.replace("resource.language.", "")
            return c

        # Kodi ≤ 19 (old layout)
        node = root.find(".//locale/language")
        if node is not None and node.text:
            return node.text.lower().strip()

        return "en_gb"

    except:
        return "en_gb"

def get_texts_for_language(proxy_cfg):
    code = get_kodi_language(proxy_cfg)
    if code in LANG:
        return LANG[code]

    short = code.split("_")[0]
    for key in LANG:
        if key.startswith(short):
            return LANG[key]

    return LANG["en_gb"]

# =====================================================================
# SQLite DB path
# =====================================================================
def get_sqlite_db_dir(proxy_cfg):
    userdata = get_userdata_path(proxy_cfg)
    return os.path.join(userdata, "Database")

# =====================================================================
# MySQL detection
# =====================================================================
def advancedsettings_exists(proxy_cfg):
    userdata = get_userdata_path(proxy_cfg)
    path = os.path.join(userdata, "advancedsettings.xml")
    return os.path.exists(path), path

def load_kodi_db_settings(proxy_cfg):
    exists, path = advancedsettings_exists(proxy_cfg)
    if not exists:
        return None
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        db = root.find("videodatabase")
        if db is None:
            return None
        return {
            "host": db.findtext("host"),
            "port": int(db.findtext("port")),
            "user": db.findtext("user"),
            "password": db.findtext("pass")
        }
    except:
        return None

def find_video_database(conn):
    cur = conn.cursor()
    cur.execute("SHOW DATABASES;")
    dbs = [x[0] for x in cur.fetchall()]

    candidates = [d for d in dbs if d.lower().startswith("video") or d.lower().startswith("myvideos")]

    if not candidates:
        print("[MySQL] No DB found")
        sys.exit(1)

    def extract_num(x):
        nums = "".join(filter(str.isdigit, x))
        return int(nums) if nums else 0

    return sorted(candidates, key=extract_num)[-1]

def get_resume_mysql(conn, dbname, file_path):
    filename = os.path.basename(file_path)
    cur = conn.cursor()

    cur.execute(f"SELECT idFile FROM {dbname}.files WHERE strFilename=%s", (filename,))
    row = cur.fetchone()
    if not row:
        return 0.0

    idFile = row[0]

    cur.execute(f"""
        SELECT timeInSeconds
        FROM {dbname}.bookmark
        WHERE idFile=%s AND type=1
    """, (idFile,))
    row = cur.fetchone()

    return float(row[0]) if row else 0.0

# =====================================================================
# SQLite Resume
# =====================================================================
def get_resume_sqlite(file_path, proxy_cfg):
    db_dir = get_sqlite_db_dir(proxy_cfg)

    try:
        files = os.listdir(db_dir)
    except:
        return 0.0

    candidates = [f for f in files if f.lower().startswith("myvideos") and f.endswith(".db")]
    if not candidates:
        return 0.0

    db_path = os.path.join(db_dir, sorted(candidates)[-1])
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    filename = os.path.basename(file_path)
    cur.execute("SELECT idFile FROM files WHERE strFilename=?", (filename,))
    row = cur.fetchone()
    if not row:
        return 0.0

    idFile = row[0]
    cur.execute("SELECT timeInSeconds FROM bookmark WHERE idFile=? AND type=1", (idFile,))
    row = cur.fetchone()

    return float(row[0]) if row else 0.0

# =====================================================================
# Detect MPC Player
# =====================================================================
def find_player_exe(exe_dir, proxy_cfg):
    players = proxy_cfg["player"]["search_names"]
    for p in players:
        full = os.path.join(exe_dir, p)
        if os.path.exists(full):
            print("[Player] Found:", full)
            return full
    print("[ERROR] No MPC player found")
    sys.exit(1)

# =====================================================================
# Resume UI
# =====================================================================
def ask_resume_choice(resume_seconds, ui_cfg, proxy_cfg):
    total = int(resume_seconds)
    time_hms = f"{total//3600:02d}:{(total%3600)//60:02d}:{total%60:02d}"

    texts = get_texts_for_language(proxy_cfg)

    colors = ui_cfg.get("colors", {})
    fonts  = ui_cfg.get("font", {})

    bg   = colors.get("background", "#000000")
    fg   = colors.get("text", "#FFFFFF")
    bnor = colors.get("button_normal", "#333333")
    bsel = colors.get("button_focus", "#1E90FF")

    f_title  = fonts.get("title_size", 48)
    f_button = fonts.get("button_size", 36)

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg=bg)
    root.attributes("-topmost", True)

    choice = {"value": None}
    def esc(event=None):
        choice["value"] = 0
        root.destroy()
    root.bind("<Escape>", esc)

    frame = tk.Frame(root, bg=bg)
    frame.pack(expand=True)

    lbl = tk.Label(
        frame,
        text=texts["resume_question"].format(time=time_hms),
        fg=fg,
        bg=bg,
        font=("Arial", f_title, "bold")
    )
    lbl.pack(pady=60)

    buttons = []

    def do_resume():
        choice["value"] = resume_seconds
        root.destroy()

    def do_restart():
        choice["value"] = 0
        root.destroy()

    if resume_seconds > 2:
        b_resume = tk.Label(
            frame,
            text=texts["resume_button"].format(time=time_hms),
            fg=fg,
            bg=bnor,
            width=20,
            height=2,
            font=("Arial", f_button)
        )
        b_resume.command = do_resume
        buttons.append(b_resume)
        b_resume.pack(pady=20)

    b_restart = tk.Label(
        frame,
        text=texts["restart"],
        fg=fg,
        bg=bnor,
        width=20,
        height=2,
        font=("Arial", f_button)
    )
    b_restart.command = do_restart
    buttons.append(b_restart)
    b_restart.pack(pady=20)

    selection = 0

    def update():
        for i, b in enumerate(buttons):
            b.configure(bg=bsel if i == selection else bnor)
    update()

    def hover(i):
        def _enter(event):
            nonlocal selection
            selection = i
            update()
        return _enter

    def click(btn):
        def _click(event):
            btn.command()
        return _click

    for i, b in enumerate(buttons):
        b.bind("<Enter>", hover(i))
        b.bind("<Button-1>", click(b))

    def key(event):
        nonlocal selection
        if event.keysym == "Down":
            selection = (selection + 1) % len(buttons)
            update()
        elif event.keysym == "Up":
            selection = (selection - 1) % len(buttons)
            update()
        elif event.keysym in ("Return", "KP_Enter"):
            buttons[selection].command()

    root.bind("<Key>", key)
    root.mainloop()

    return 0 if choice["value"] is None else choice["value"]

# =====================================================================
# Launch MPC Player
# =====================================================================
def start_player(player, video, resume):
    cmd = [player, video]
    if resume > 2:
        cmd += ["/startpos", str(resume)]
    subprocess.Popen(cmd).wait()

# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: mpc_proxy.exe <video file>")
        sys.exit(1)

    video = sys.argv[1]
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    proxy_cfg = load_proxy_config(exe_dir)
    ui_cfg = proxy_cfg["ui"]

    player_exe = find_player_exe(exe_dir, proxy_cfg)

    mysql_cfg = load_kodi_db_settings(proxy_cfg)

    if mysql_cfg:
        try:
            conn = pymysql.connect(
                host=mysql_cfg["host"],
                port=mysql_cfg["port"],
                user=mysql_cfg["user"],
                password=mysql_cfg["password"]
            )
            dbname = find_video_database(conn)
            resume = get_resume_mysql(conn, dbname, video)
        except:
            resume = get_resume_sqlite(video, proxy_cfg)
    else:
        resume = get_resume_sqlite(video, proxy_cfg)

    if resume < ui_cfg["min_resume_seconds"]:
        resume = 0
    else:
        resume = ask_resume_choice(resume, ui_cfg, proxy_cfg)

    start_player(player_exe, video, resume)
