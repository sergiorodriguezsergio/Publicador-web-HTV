import json
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_DIR, "config")
PROMPTS_PATH = os.path.join(CONFIG_DIR, "prompts.json")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")


def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"watch_folder": ""}


def save_settings(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def center_on_parent(win, parent, w, h):
    parent.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()

    # Ajuste responsivo: evita que los diálogos excedan la pantalla.
    final_w = max(360, min(w, int(sw * 0.92)))
    final_h = max(220, min(h, int(sh * 0.90)))

    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    x = px + (pw - final_w) // 2
    y = py + (ph - final_h) // 2
    x = max(0, min(x, sw - final_w))
    y = max(0, min(y, sh - final_h))
    win.geometry(f"{final_w}x{final_h}+{x}+{y}")
