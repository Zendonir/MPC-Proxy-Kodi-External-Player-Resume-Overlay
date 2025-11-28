# MPC Proxy – Kodi External Player Resume Overlay

**MPC Proxy** is a lightweight Windows proxy for Kodi that replaces Kodi’s internal video player with **MPC-HC or MPC-BE**.  
It automatically reads the resume point from Kodi’s SQLite or MySQL video database and displays a **Kodi-style fullscreen resume dialog** before launching the external player.

The UI supports **keyboard and mouse navigation**, closely mimicking the original **Kodi Estuary** experience.

No modifications to Kodi itself are required — simply configure the proxy as your external player.

---

## ✨ Features

### Database Integration
- Automatic detection of:
  - **Kodi MySQL** video database via `advancedsettings.xml`
  - **Local SQLite** Kodi database (fallback)
- Reads the correct resume bookmark (`type = 1`), just like Kodi

### Kodi-Style Resume Dialog
- Fullscreen, Estuary-inspired design  
- **Keyboard navigation:**  
  - Up / Down — change selection  
  - Enter — confirm  
  - Esc — start from the beginning  
- **Mouse navigation:**  
  - Hover = focus  
  - Click = execute  
- Time display in **HH:MM:SS** format  
- Color theme and typography fully configurable

### Highly Configurable
- All UI colors, font sizes, and layout defined in **`MPC_Proxy_config.json`**
- Customizable **minimum resume threshold** (e.g., skip dialog if less than 120s)
- Configurable external player search order (MPC-HC / MPC-BE)

### Robust Path Handling
- Supports:
  - UNC paths (`\\server\share`)
  - Mapped drive paths (`Z:\Movies\...`)
  - Local absolute paths
- Normalizes paths similar to Kodi
- Clean fallback logic for missing configuration files

### Transparent Kodi Integration
- Acts as a drop-in external player wrapper  
- No Kodi skin or core modifications required  
- Kodi passes the file path → proxy shows resume dialog → MPC plays

---

## ⚙ Configuration (MPC_Proxy_config.json)

Example:

```json
{
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
  }
}
