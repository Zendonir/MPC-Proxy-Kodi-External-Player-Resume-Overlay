import os
import sys
import json
import subprocess
import pymysql
import sqlite3
import xml.etree.ElementTree as ET
import tkinter as tk

# =====================================================================
# Default-Konfiguration (wird genutzt, wenn MPC_Proxy_config.json fehlt
# oder Felder daraus fehlen)
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
# Proxy-Config laden (MPC_Proxy_config.json im EXE-Ordner)
# =====================================================================
def load_proxy_config(base_dir):
    cfg_path = os.path.join(base_dir, "MPC_Proxy_config.json")
    if not os.path.exists(cfg_path):
        print("[WARN] MPC_Proxy_config.json nicht gefunden → nutze Default-Konfiguration.")
        return DEFAULT_PROXY_CONFIG

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = merge_dict(DEFAULT_PROXY_CONFIG, user_cfg)
        print("[INFO] MPC_Proxy_config.json geladen.")
        return cfg
    except Exception as e:
        print(f"[WARN] Fehler beim Laden von MPC_Proxy_config.json: {e}")
        print("[WARN] Nutze Default-Konfiguration.")
        return DEFAULT_PROXY_CONFIG

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
# Resume aus MySQL holen (gefixt)
# =====================================================================
def get_resume_mysql(conn, dbname, file_path):
    folder, filename = os.path.split(file_path)
    folder_norm = folder.replace("\\", "/") + "/"

    print(f"[MySQL] Ordner (Kodi erwartet ähnliches): {folder_norm}")
    print(f"[MySQL] Datei:                          {filename}")

    cur = conn.cursor()

    # idFile suchen – aktuell über Dateiname
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

    # Bookmark suchen – wie in SQLite: type = 1 bevorzugen
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

    candidates = [f for f in os.listdir(db_dir) if f.lower().startswith("myvideos") and f.lower().endswith(".db")]
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
    # Aus Config lesen, sonst Default
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
# FULLSCREEN Resume-Fenster (mit Config, Tastatursteuerung)
# =====================================================================
def ask_resume_choice(resume_seconds, ui_cfg):
    print(f"[UI] Resume-Position (raw): {resume_seconds}")

    total = int(resume_seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    hms = f"{h:02d}:{m:02d}:{s:02d}"

    colors = ui_cfg.get("colors", {})
    fonts  = ui_cfg.get("font", {})

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

    # ESC = von vorne
    def on_escape(event=None):
        nonlocal choice
        choice["value"] = 0
        root.destroy()
    root.bind("<Escape>", on_escape)

    frame = tk.Frame(root, bg=bg_color)
    frame.pack(expand=True)

    msg = f"Fortsetzen ab {hms}?" if resume_seconds > 0 else "Von vorne starten?"

    label = tk.Label(
        frame,
        text=msg,
        fg=text_color,
        bg=bg_color,
        font=("Arial", title_size, "bold")
    )
    label.pack(pady=60)

    choice = {"value": None}

    def start_new():
        choice["value"] = 0
        root.destroy()

    def resume():
        choice["value"] = resume_seconds
        root.destroy()

    buttons = []

    # -----------------------
    # BUTTON ERZEUGUNG
    # -----------------------
    if resume_seconds > 2:
        btn_resume = tk.Label(
            frame,
            text=f"Weiter bei {hms}",
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
        text="Von vorne starten",
        font=("Arial", button_size),
        bg=btn_normal,
        fg=text_color,
        width=20,
        height=2
    )
    btn_new.command = start_new
    buttons.append(btn_new)
    btn_new.pack(pady=20)

    # -----------------------
    # FOKUS- UND HIGHLIGHT-LOGIK
    # -----------------------
    selection_index = 0

    def update_selection():
        for i, b in enumerate(buttons):
            b.configure(bg=btn_focus if i == selection_index else btn_normal)

    update_selection()

    # -----------------------
    # MAUS: Hover → Fokus setzen
    # -----------------------
    def make_on_enter(i):
        def _on_enter(event):
            nonlocal selection_index
            selection_index = i
            update_selection()
        return _on_enter

    # MAUS: Klick → Aktion ausführen
    def make_on_click(button):
        def _on_click(event):
            button.command()
        return _on_click

    for i, b in enumerate(buttons):
        b.bind("<Enter>", make_on_enter(i))
        b.bind("<Button-1>", make_on_click(b))

    # -----------------------
    # TASTATUR: ↑ ↓ ENTER
    # -----------------------
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

    return choice["value"] if choice["value"] is not None else 0


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
        print("Verwendung: proxy.exe <Videodatei>")
        sys.exit(1)

    video = sys.argv[1]
    print("Eingangspfad von Kodi:", video)

    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    # Proxy-Config laden (mit Fallback)
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

    # Wenn Resume < min_resume_seconds → Direkt starten, ohne Overlay
    if resume < min_resume:
        print(f"[INFO] Resume ({resume}s) < {min_resume}s → ohne Nachfrage direkt von vorne starten.")
        resume = 0
    else:
        resume = ask_resume_choice(resume, ui_cfg)

    start_player(player_exe, video, resume)
