# MPC Proxy – Kodi External Player Resume Overlay

**MPC Proxy** is a lightweight Windows proxy for Kodi that replaces Kodi’s internal video player with **MPC-HC or MPC-BE**.  
It automatically reads the resume point from Kodi’s SQLite or MySQL video database and displays a **Kodi-style fullscreen resume dialog** before launching the external player.

The UI supports **keyboard and mouse navigation**, closely mimicking the original **Kodi Estuary** experience.

No modifications to Kodi itself are required — simply configure the proxy as your external player.

---

## ✨ Features

### Database Integration
- Automatically detects:
  - **Kodi MySQL** video database via `advancedsettings.xml`
  - **Local SQLite** Kodi database (fallback)
- Reads the correct resume bookmark (`type = 1`), matching Kodi’s own behavior.

### Kodi-Style Resume Dialog
- Fullscreen Estuary-style resume screen  
- **Keyboard navigation**:  
  - Up / Down = select  
  - Enter = confirm  
  - Esc = start from beginning  
- **Mouse navigation**:  
  - Hover = focus  
  - Click = execute  
- Resume point shown in **HH:MM:SS** format  
- UI fully themeable via JSON

### Highly Configurable
- All UI colors, font sizes, and logic defined in **`mpc_proxy_config.json`**
- Adjustable **minimum resume threshold** (e.g., skip dialog if <120s)
- MPC player autodetection (MPC-HC, MPC-BE, 32/64-bit)

### Robust Path Handling
- Supports:
  - UNC paths (`\\server\share`)
  - Mapped drives (`Z:\Movies\...`)
  - Local paths  
- Normalizes paths similar to Kodi  
- Clean fallback logic for missing config files

### Seamless Kodi Integration
- Works as a transparent external player wrapper  
- Kodi → Proxy → Resume Dialog → MPC  
- No modifications to Kodi skin or core required

---

## ⚙ Configuration (mpc_proxy_config.json)

Place `mpc_proxy_config.json` **next to** `mpc_proxy.exe`.

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
```
If the config file is missing, defaults are used automatically.

---

# Installation (Complete Guide)

## 1. Place the proxy inside the MPC player directory

Copy mpc_proxy.exe into the same folder as MPC-HC or MPC-BE.

Example:

C:\Media\MPC-HC\
 ├── mpc_proxy.exe
 ├── mpc_proxy_config.json
 ├── mpc-hc64.exe
 ├── mpc-hc.exe
 ├── mpc-be64.exe
 └── mpc-be.exe

The proxy automatically detects the correct MPC player.

---

## 2. Integrate MPC Proxy into Kodi

Create or edit:

%APPDATA%\Kodi\userdata\playercorefactory.xml

Example:
```playercorefactory
<playercorefactory>
    <players>
        <player
            name="MPCProxy"
            type="ExternalPlayer"
            audio="false"
            video="true">
            <filename>C:\Path\To\mpc_proxy.exe</filename>
            <args>"{1}"</args>
            <hidexbmc>true</hidexbmc>
            <hideconsole>false</hideconsole>
            <warpcursor>none</warpcursor>
        </player>
    </players>

    <rules action="prepend">
        <rule filetypes="mkv|mp4|avi|mov|wmv" player="MPCProxy" />
    </rules>
</playercorefactory>
```
---

## 3. Restart Kodi

Kodi will now use MPC Proxy for all configured video formats.
