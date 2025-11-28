# MPC Proxy – Kodi External Player Resume Overlay
# Vollständiges Script mit:
# - MySQL / SQLite Resume
# - MPC-HC / MPC-BE Erkennung
# - Konfigurierbare UI aus mpc_proxy_config.json
# - Mehrsprachigem Overlay (Sprache aus Kodi)
# - Tastatur + Maus Bedienung

import os
import sys
import json
import subprocess
import pymysql
import sqlite3
import xml.etree.ElementTree as ET
import tkinter as tk

# =====================================================================
# Default-Konfiguration (wird genutzt, wenn mpc_proxy_config.json fehlt
# oder Einträge darin fehlen)
# =====================================================================
DEFAULT_PROXY_CONFIG = {
    "ui": {
        "min_resume_seconds": 120,
        "colors": {
            "background": "#000000",
            "text": "#FFFFFF",
            "button_normal": "#333333",
            "button_focus": "#1E90FF",
            "accent": "#1E90FF",
        },
        "font": {
            "title_size": 48,
            "button_size": 36,
        },
    },
    "player": {
        "search_names": [
            "mpc-hc64.exe",
            "mpc-hc.exe",
            "mpc-be64.exe",
            "mpc-be.exe",
        ]
    }
}

# =====================================================================
# Sprach-Tabelle (UI-Texte für verschiedene Kodi-Sprachen)
# =====================================================================
LANG = {
    "en_gb": {
        "resume_question": "Resume from {time}?",
        "resume_button": "Resume at {time}",
        "restart": "Start from beginning",
    },
    "en_us": {
        "resume_question": "Resume from {time}?",
        "resume_button": "Resume at {time}",
        "restart": "Start from beginning",
    },
    "de_de": {
        "resume_question": "Fortsetzen ab {time}?",
        "resume_button": "Weiter bei {time}",
        "restart": "Von vorne starten",
    },
    "fr_fr": {
        "resume_question": "Reprendre à {time} ?",
        "resume_button": "Reprendre à {time}",
        "restart": "Recommencer depuis le début",
    },
    "es_es": {
        "resume_question": "Reanudar desde {time}?",
        "resume_button": "Reanudar en {time}",
        "restart": "Empezar desde el principio",
    },
    "it_it": {
        "resume_question": "Riprendere da {time}?",
        "resume_button": "Riprendi a {time}",
        "restart": "Ricomincia dall'inizio",
    },
    "pt_br": {
        "resume_question": "Retomar de {time}?",
        "resume_button": "Retomar em {time}",
        "restart": "Começar do início",
    },
    "pt_pt": {
        "resume_question": "Retomar desde {time}?",
        "resume_button": "Retomar em {time}",
        "restart": "Começar do início",
    },
    "nl_nl": {
        "resume_question": "Hervatten vanaf {time}?",
        "resume_button": "Hervatten op {time}",
        "restart": "Opnieuw starten",
    },
    "pl_pl": {
        "resume_question": "Wznawiać od {time}?",
        "resume_button": "Wznów o {time}",
        "restart": "Zacznij od początku",
    },
    "tr_tr": {
        "resume_question": "{time} konumundan devam edilsin mi?",
        "resume_button": "{time} konumundan devam et",
        "restart": "Baştan başla",
    },
}

# =====================================================================
# Hilfsfunktion: rekursives Mergen von Dicts
# =====================================================================
def merge_dict(default, custom):
    """
    Nimmt default-Dict und überschreibt Werte mit custom,
    fehlende Keys bleiben aus default erhalten.
    """
    if not isinstance(custom, dict):
        return default
    result = dict(default)
    for k, v in custom.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = v
    return result

# =====================================================================
# Proxy-Config laden (mpc_proxy_config.json im EXE-Ordner)
# =====================================================================
def load_proxy_config(base_dir):
    cfg_path = os.path.join(base_dir, "mpc_proxy_config.json")
    if not os.path.exists(cfg_path):
        print("[WARN] mpc_proxy_config.json nicht gefunden → nutze Default-Konfiguration.")
        return DEFAULT_PROXY_CONFIG

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = merge_dict(DEFAULT_PROXY_CONFIG, user_cfg)
        print("[INFO] mpc_proxy_config.json geladen.")
        return cfg
    except Exception as e:
        print(f"[WARN] Fehler beim Laden von mpc_proxy_config.json: {e}")
        print("[WARN] Nutze Default-Konfiguration.")
        return DEFAULT_PROXY_CONFIG

# =====================================================================
# Kodi-Sprache aus guisettings.xml ermitteln
# =====================================================================
def get_kodi_language():
    """
    Liest die Sprache aus Kodi aus.
    Unterstützt:
      - Kodi >= 20  (resource.language.xx_xx)
      - Kodi <= 19  (locale/language Struktur)
      - Fallback auf en_gb
    """

    path = os.path.join(
        os.getenv("APPDATA"),
        "Kodi",
        "userdata",
        "guisettings.xml"
    )

    if not os.path.exists(path):
        print("[INFO] guisettings.xml nicht gefunden → Sprache = en_gb")
        return "en_gb"

    try:
        tree = ET.parse(path)
        root = tree.getroot()

        # ---------------------------------------------------------
        # 1) Neue Kodi-Versionen: <setting id="locale.language">
        # ---------------------------------------------------------
        setting_lang = root.find('.//setting[@id="locale.language"]')
        if setting_lang is not None and setting_lang.text:
            code = setting_lang.text.strip().lower()
            print("[DEBUG] Kodi Sprache (Setting):", code)

            # normalize "resource.language.de_de" → "de_de"
            if code.startswith("resource.language."):
                code = code.replace("resource.language.", "")

            return code

        # ---------------------------------------------------------
        # 2) Alte Kodi-Versionen: <locale><language>de_de</language></locale>
        # ---------------------------------------------------------
        legacy_lang = root.find(".//locale/language")
        if legacy_lang is not None and legacy_lang.text:
            code = legacy_lang.text.strip().lower()
            print("[DEBUG] Kodi Sprache (Legacy):", code)
            return code

        # ---------------------------------------------------------
        # 3) Ultimativer Fallback
        # ---------------------------------------------------------
        print("[INFO] Keine Kodi-Sprache gefunden → fallback = en_gb")
        return "en_gb"

    except Exception as e:
        print(f"[WARN] Fehler beim Lesen der Kodi Sprache: {e} → fallback = en_gb")
        return "en_gb"


def get_texts_for_language():
    code = get_kodi_language()
    if code in LANG:
        return LANG[code]
    # fallback auf Sprache ohne Region, z.B. "en" aus "en_us"
    short = code.split("_")[0]
    for key in LANG.keys():
        if key.startswith(short):
            return LANG[key]
    return LANG["en_gb"]

# =====================================================================
# Prüfen ob advancedsettings.xml existiert
# =====================================================================
def advancedsettings_exists():
    xml_path = os.path.join(
        os.getenv("APPDATA"),
        "Kodi",
        "userdata",
        "advancedsettings.xml"
    )
    return os.path.exists(xml_path), xml_path

# =====================================================================
# Kodi DB Settings automatisch lesen (MySQL)
# =====================================================================
def load_kodi_db_settings():
    exists, xml_path = advancedsettings_exists()
    if not exists:
        print("[INFO] Keine advancedsettings.xml → MySQL deaktiviert.")
        return None

    tree = ET.parse(xml_path)
    root = tree.getroot()

    db = root.find("videodatabase")
    if db is None:
        print("[WARN] advancedsettings.xml vorhanden, aber <videodatabase> fehlt.")
        return None

    print("[INFO] MySQL-Konfiguration gefunden.")
    return {
        "host": db.findtext("host"),
        "port": int(db.findtext("port")),
        "user": db.findtext("user"),
        "password": db.findtext("pass"),
    }

# =====================================================================
# Automatisch Kodi Video-DB erkennen (MySQL)
# =====================================================================
def find_video_database(conn):
    cur = conn.cursor()
    cur.execute("SHOW DATABASES;")
    dbs = [row[0] for row in cur.fetchall()]

    candidates = [d for d in dbs if d.lower().startswith("video") or d.lower().startswith("myvideos")]

    if not candidates:
        print("Keine Video-Datenbank gefunden!")
        sys.exit(1)

    candidates_sorted = sorted(
        candidates,
        key=lambda x: ''.join(filter(str.isdigit, x)) or "0"
    )

    selected = candidates_sorted[-1]
    print("Gefundene Kodi Video-DB:", selected)
    return selected

# =====================================================================
# Resume aus MySQL holen
# =====================================================================
def get_resume_mysql(conn, dbname, file_path):
    folder, filename = os.path.split(file_path)
    folder_norm = folder.replace("\\", "/") + "/"

    print(f"[MySQL] Ordner (Kodi erwartet ähnliches): {folder_norm}")
    print(f"[MySQL] Datei:                          {filename}")

    cur = conn.cursor()
    idFile = None

    try:
        cur.execute(
            f"""
            SELECT f.idFile
            FROM {dbname}.files f
            JOIN {dbname}.path p ON f.idPath = p.idPath
            WHERE f.strFilename=%s
            """,
            (filename,)
        )
        rows = cur.fetchall()
        print(f"[MySQL] Gefundene idFile-Kandidaten für '{filename}': {[r[0] for r in rows]}")
        if rows:
            idFile = rows[0][0]
    except Exception as e:
        print("[MySQL] Fehler bei idFile-Suche:", e)

    if idFile is None:
        print("[MySQL] idFile nicht gefunden → Resume=0")
        return 0.0

    cur.execute(
        f"""
        SELECT timeInSeconds, type, player
        FROM {dbname}.bookmark
        WHERE idFile=%s AND type=1
        ORDER BY timeInSeconds DESC
        """,
        (idFile,)
    )
    row = cur.fetchone()

    if not row:
        print("[MySQL] Kein Bookmark mit type=1 gefunden, versuche beliebigen Bookmark …")
        cur.execute(
            f"""
            SELECT timeInSeconds, type, player
            FROM {dbname}.bookmark
            WHERE idFile=%s
            ORDER BY timeInSeconds DESC
            """,
            (idFile,)
        )
        row = cur.fetchone()

    if not row:
        print("[MySQL] Überhaupt kein Bookmark gefunden → 0")
        return 0.0

    resume = float(row[0])
    b_type = row[1]
    b_player = row[2]
    print(f"[MySQL] Bookmark gefunden: time={resume}  type={b_type}  player='{b_player}'")
    return resume

# =====================================================================
# Resume aus SQLite holen (Fallback)
# =====================================================================
def get_resume_sqlite(file_path):
    db_dir = os.path.join(os.getenv("APPDATA"), "Kodi", "userdata", "Database")

    try:
        candidates = [f for f in os.listdir(db_dir) if f.lower().startswith("myvideos") and f.lower().endswith(".db")]
    except FileNotFoundError:
        print("[SQLite] Datenbankordner nicht gefunden → 0")
        return 0.0

    if not candidates:
        print("[SQLite] Keine lokale Kodi-DB gefunden!")
        return 0.0

    dbname = sorted(candidates)[-1]
    db_path = os.path.join(db_dir, dbname)

    print("[SQLite] Verwende lokale DB:", db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    filename = os.path.basename(file_path)
    folder = os.path.dirname(file_path).replace("\\", "/") + "/"

    print("[SQLite] Dateiname:", filename)

    cur.execute("SELECT idFile, idPath FROM files WHERE strFilename=?", (filename,))
    row = cur.fetchone()

    if not row:
        print("[SQLite] Datei nicht gefunden → 0")
        return 0.0

    idFile = row[0]
    idPath = row[1]
    print(f"[SQLite] idFile={idFile}, idPath={idPath}")

    cur.execute("SELECT strPath FROM path WHERE idPath=?", (idPath,))
    row = cur.fetchone()
    if not row:
        print("[SQLite] Pfad nicht gefunden → 0")
        return 0.0
    print(f"[SQLite] Pfad in DB: {row[0]}")

    cur.execute("SELECT timeInSeconds, type FROM bookmark WHERE idFile=? AND type=1", (idFile,))
    row = cur.fetchone()

    if not row:
        print("[SQLite] Kein Resume (type=1) gefunden → 0")
        return 0.0

    resume = float(row[0])
    b_type = row[1]
    print(f"[SQLite] Resume gefunden: time={resume}  type={b_type}")
    return resume

# =====================================================================
# MPC-HC / MPC-BE automatisch erkennen (optional via Config)
# =====================================================================
def find_player_exe(exe_dir, proxy_cfg):
    player_cfg = proxy_cfg.get("player", {})
    candidates = player_cfg.get("search_names", DEFAULT_PROXY_CONFIG["player"]["search_names"])

    for exe in candidates:
        candidate = os.path.join(exe_dir, exe)
        if os.path.exists(candidate):
            print("Benutze Player:", candidate)
            return candidate

    print("FEHLER: Kein MPC-HC oder MPC-BE im Proxy-Ordner gefunden!")
    sys.exit(1)

# =====================================================================
# FULLSCREEN Resume-Fenster (mit Config, Maus + Tastatur, Mehrsprachig)
# =====================================================================
def ask_resume_choice(resume_seconds, ui_cfg):
    print(f"[UI] Resume-Position (raw): {resume_seconds}")

    total = int(resume_seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    hms = f"{h:02d}:{m:02d}:{s:02d}"

    texts = get_texts_for_language()

    colors = ui_cfg.get("colors", {})
    fonts = ui_cfg.get("font", {})

    bg_color   = colors.get("background", "#000000")
    text_color = colors.get("text", "#FFFFFF")
    btn_normal = colors.get("button_normal", "#333333")
    btn_focus  = colors.get("button_focus", "#1E90FF")

    title_size  = fonts.get("title_size", 48)
    button_size = fonts.get("button_size", 36)

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg=bg_color)
    root.focus_set()

    choice = {"value": None}

    def on_escape(event=None):
        choice["value"] = 0
        root.destroy()

    root.bind("<Escape>", on_escape)

    frame = tk.Frame(root, bg=bg_color)
    frame.pack(expand=True)

    msg = texts["resume_question"].format(time=hms)

    label = tk.Label(
        frame,
        text=msg,
        fg=text_color,
        bg=bg_color,
        font=("Arial", title_size, "bold")
    )
    label.pack(pady=60)

    def start_new():
        choice["value"] = 0
        root.destroy()

    def resume():
        choice["value"] = resume_seconds
        root.destroy()

    buttons = []

    if resume_seconds > 2:
        btn_resume = tk.Label(
            frame,
            text=texts["resume_button"].format(time=hms),
            font=("Arial", button_size),
            bg=btn_normal,
            fg=text_color,
            width=20,
            height=2
        )
        btn_resume.command = resume
        buttons.append(btn_resume)
        btn_resume.pack(pady=20)

    btn_new = tk.Label(
        frame,
        text=texts["restart"],
        font=("Arial", button_size),
        bg=btn_normal,
        fg=text_color,
        width=20,
        height=2
    )
    btn_new.command = start_new
    buttons.append(btn_new)
    btn_new.pack(pady=20)

    selection_index = 0

    def update_selection():
        for i, b in enumerate(buttons):
            b.configure(bg=btn_focus if i == selection_index else btn_normal)

    update_selection()

    def make_on_enter(i):
        def _on_enter(event):
            nonlocal selection_index
            selection_index = i
            update_selection()
        return _on_enter

    def make_on_click(button):
        def _on_click(event):
            button.command()
        return _on_click

    for i, b in enumerate(buttons):
        b.bind("<Enter>", make_on_enter(i))
        b.bind("<Button-1>", make_on_click(b))

    def on_key(event):
        nonlocal selection_index

        if event.keysym == "Down":
            selection_index = (selection_index + 1) % len(buttons)
            update_selection()
        elif event.keysym == "Up":
            selection_index = (selection_index - 1) % len(buttons)
            update_selection()
        elif event.keysym in ("Return", "KP_Enter"):
            buttons[selection_index].command()

    root.bind("<Key>", on_key)

    root.mainloop()

    if choice["value"] is None:
        return 0
    return choice["value"]

# =====================================================================
# MPC starten
# =====================================================================
def start_player(player_path, video_file, resume_seconds):
    cmd = [player_path, video_file]

    if resume_seconds > 2:
        cmd += ["/startpos", str(resume_seconds)]

    print("Starte Player mit:", cmd)
    proc = subprocess.Popen(cmd)
    proc.wait()
    print("Player beendet:", proc.returncode)

# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Verwendung: mpc_proxy.exe <Videodatei>")
        sys.exit(1)

    video = sys.argv[1]
    print("Eingangspfad von Kodi:", video)

    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    proxy_cfg = load_proxy_config(exe_dir)
    ui_cfg = proxy_cfg.get("ui", {})
    min_resume = ui_cfg.get("min_resume_seconds", DEFAULT_PROXY_CONFIG["ui"]["min_resume_seconds"])

    player_exe = find_player_exe(exe_dir, proxy_cfg)

    cfg = load_kodi_db_settings()
    resume = 0.0

    if cfg:
        try:
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"]
            )
            dbname = find_video_database(conn)
            resume = get_resume_mysql(conn, dbname, video)
        except Exception as e:
            print("[MySQL] Fehler:", e)
            print("[INFO] Fallback auf lokale SQLite-DB.")
            resume = get_resume_sqlite(video)
    else:
        resume = get_resume_sqlite(video)

    if resume < min_resume:
        print(f"[INFO] Resume ({resume}s) < {min_resume}s → ohne Nachfrage direkt von vorne starten.")
        resume = 0
    else:
        resume = ask_resume_choice(resume, ui_cfg)

    start_player(player_exe, video, resume)
