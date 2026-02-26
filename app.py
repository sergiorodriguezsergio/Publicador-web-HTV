"""
HTV · Publicador Inteligente
UI wizard paso-a-paso con file watcher automático.
"""

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import threading
import json
import os
import shutil
import webbrowser
import re
import time
import queue
from html.parser import HTMLParser
from datetime import datetime

# ─── Paleta de colores ───────────────────────────────────────────
BG_DARK       = "#15170d"
BG_CARD       = "#161b22"
BG_CARD_SOFT  = "#1b222c"
BG_INPUT      = "#0d1117"
BG_HEADER     = "#0d1a33"
BORDER        = "#21262d"
BORDER_BRIGHT = "#30363d"
SHADOW_DARK   = "#0a0f14"
ACCENT_BLUE   = "#58a6ff"
ACCENT_CYAN   = "#39d0f0"
ACCENT_GREEN  = "#3fb950"
ACCENT_RED    = "#f85149"
ACCENT_PURPLE = "#bc8cff"
ACCENT_YELLOW = "#d29922"
ACCENT_ORANGE = "#ffb86b"
ACCENT_GOLD   = "#f5c451"
FG_PRIMARY    = "#e6edf3"
FG_SECONDARY  = "#8b949e"
FG_MUTED      = "#484f58"
FONT_FAMILY   = "Segoe UI"

# Los servicios se cargan de forma diferida en la Splash Screen
TranscriptionService = None
WriterService = None
PublisherService = None
VerificationService = None
HAS_WATCHDOG = False
Observer = None
FileSystemEventHandler = object
Mp3Handler = None

# ─── Splash Screen ────────────────────────────────────────────────
class SplashScreen(tk.Toplevel):
    """Ventana inicial de carga para mejorar la experiencia de usuario."""
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG_DARK)
        
        w, h = 450, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        
        main_f = tk.Frame(self, bg=BG_DARK, highlightthickness=1, highlightbackground=ACCENT_CYAN)
        main_f.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(main_f, text="📺", font=("Segoe UI Emoji", 50), bg=BG_DARK, fg=ACCENT_CYAN).pack(pady=(40, 10))
        tk.Label(main_f, text="HTV · PUBLICADOR WEB", font=(FONT_FAMILY, 16, "bold"), bg=BG_DARK, fg="white").pack()
        tk.Label(main_f, text="SISTEMA INTELIGENTE DE REDACCIÓN", font=(FONT_FAMILY, 8), bg=BG_DARK, fg=ACCENT_CYAN).pack(pady=(2, 20))
        
        self.lbl_status = tk.Label(main_f, text="Iniciando componentes...", font=(FONT_FAMILY, 9), bg=BG_DARK, fg=FG_SECONDARY)
        self.lbl_status.pack()
        
        self.canvas = tk.Canvas(main_f, width=300, height=2, bg=BG_CARD, highlightthickness=0)
        self.canvas.pack(pady=15)
        self.progress = self.canvas.create_rectangle(0, 0, 0, 2, fill=ACCENT_CYAN, outline="")
        
        self._progress_val = 0
        self._anim_id = None
        self._animate()

    def _animate(self):
        try:
            if not self.winfo_exists(): return
            if self._progress_val < 300:
                self._progress_val += 4
                self.canvas.coords(self.progress, 0, 0, self._progress_val, 2)
                self._anim_id = self.after(30, self._animate)
        except (tk.TclError, RuntimeError):
            pass

    def destroy(self):
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except Exception: pass
        super().destroy()

    def update_status(self, text):
        self.lbl_status.config(text=text)
        self.update()

def load_resources(splash):
    """Carga los módulos pesados en un hilo secundario."""
    global TranscriptionService, WriterService, PublisherService, VerificationService
    global HAS_WATCHDOG, Observer, FileSystemEventHandler, Mp3Handler
    
    try:
        splash.update_status("Cargando servicios de IA...")
        from core.transcription import TranscriptionService
        from core.writer import WriterService
        from core.publisher import PublisherService
        from core.verification import VerificationService
        
        splash.update_status("Iniciando vigilante de archivos...")
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            HAS_WATCHDOG = True
            
            class _Mp3Handler(FileSystemEventHandler):
                def __init__(self, callback):
                    super().__init__()
                    self._callback = callback
                    self._processed = set()

                _EXTS = {".mp4", ".mp3", ".wav", ".m4a", ".ogg",
                         ".flac", ".webm", ".mpeg", ".mpg", ".mov"}

                def on_created(self, event):
                    if event.is_directory: return
                    raw = event.src_path
                    src = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    if os.path.splitext(src)[1].lower() in self._EXTS:
                        if src in self._processed: return
                        self._processed.add(src)
                        threading.Thread(target=self._wait_stable, args=(src,), daemon=True).start()

                def _wait_stable(self, path):
                    prev = -1
                    for _ in range(60):
                        try:
                            sz = os.path.getsize(path)
                            if sz == prev and sz > 0:
                                self._callback(path)
                                return
                            prev = sz
                        except OSError: pass
                        time.sleep(1)
            
            Mp3Handler = _Mp3Handler
        except ImportError:
            HAS_WATCHDOG = False
            Observer = None
            FileSystemEventHandler = object
            Mp3Handler = None

        splash.update_status("¡Todo listo!")
        time.sleep(0.5)
    except Exception as e:
        print(f"Error en carga: {e}")

CONFIG_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
PROMPTS_PATH  = os.path.join(CONFIG_DIR, "prompts.json")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")


# ─── Settings helpers ────────────────────────────────────────────
def _load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"watch_folder": ""}


def _save_settings(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _center_on_parent(win, parent, w, h):
    """Centra una ventana Toplevel sobre la ventana padre."""
    parent.update_idletasks()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 2
    win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


# ─── Canvas: rectángulo redondeado ───────────────────────────────
def _rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Dibuja un rectángulo con esquinas redondeadas en un Canvas."""
    pts = [
        x1 + r, y1,  x2 - r, y1,
        x2, y1,      x2, y1 + r,
        x2, y2 - r,  x2, y2,
        x2 - r, y2,  x1 + r, y2,
        x1, y2,      x1, y2 - r,
        x1, y1 + r,  x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


# ─── RoundedText: Text con borde redondeado ─────────────────────
class RoundedText(tk.Canvas):
    """tk.Text envuelto en un Canvas que dibuja borde redondeado."""

    def __init__(self, parent, text_height=2, radius=10,
                 border_color=BORDER_BRIGHT, focus_color=ACCENT_CYAN,
                 bg_fill=BG_INPUT, **text_kw):
        font = text_kw.get("font", (FONT_FAMILY, 10))
        fsize = font[1] if isinstance(font, tuple) and len(font) > 1 else 10
        canvas_h = int(text_height * fsize * 2.0) + 18

        pbg = parent.cget("bg")
        super().__init__(parent, bg=pbg, highlightthickness=0, height=canvas_h)

        self._r = radius
        self._border = border_color
        self._focus = focus_color
        self._fill = bg_fill
        self._focused = False

        self.text = tk.Text(
            self, height=text_height, bg=bg_fill,
            relief=tk.FLAT, highlightthickness=0, borderwidth=0,
            padx=10, pady=6, **text_kw,
        )
        self._win = self.create_window(0, 0, window=self.text, anchor="nw")

        self.bind("<Configure>", self._redraw)
        self.text.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.text.bind("<FocusOut>", lambda e: self._set_focus(False))

    def _set_focus(self, val):
        self._focused = val
        self._redraw()

    def _redraw(self, event=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 6 or h < 6:
            return
        self.delete("border")
        color = self._focus if self._focused else self._border
        _rounded_rect(
            self, 2, 2, w - 2, h - 2, self._r,
            outline=color, fill=self._fill, width=1.5, tags="border",
        )
        self.tag_lower("border")
        pad = 6
        self.coords(self._win, pad + 2, pad)
        self.itemconfig(self._win, width=max(1, w - 2 * pad - 4),
                        height=max(1, h - 2 * pad))


# ─── Toggle switch ──────────────────────────────────────────────
class ToggleSwitch(tk.Canvas):
    """Interruptor animado tipo iOS."""

    def __init__(self, parent, command=None, initial=False,
                 width=48, height=24, bg_on=ACCENT_GREEN, bg_off=FG_MUTED):
        super().__init__(parent, width=width, height=height,
                         bg=parent.cget("bg"), highlightthickness=0, cursor="hand2")
        self._on = initial
        self._cmd = command
        self._sw, self._sh = width, height
        self._bg_on, self._bg_off = bg_on, bg_off
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def _toggle(self, e=None):
        self._on = not self._on
        self._draw()
        if self._cmd:
            self._cmd(self._on)

    def _draw(self):
        self.delete("all")
        w, h = self._sw, self._sh
        r = h // 2
        bg = self._bg_on if self._on else self._bg_off
        _rounded_rect(self, 1, 1, w - 1, h - 1, r, fill=bg, outline=bg)
        pad = 3
        kr = r - pad
        cx = w - r if self._on else r
        self.create_oval(cx - kr, pad, cx + kr, h - pad, fill="white", outline="white")

    @property
    def is_on(self):
        return self._on

    def set(self, val):
        self._on = bool(val)
        self._draw()


# ─── Indicador de pasos ─────────────────────────────────────────
class StepIndicator(tk.Canvas):
    STEPS = [("🎙", "Audio"), ("🤖", "Procesar"), ("📝", "Editar"), ("🚀", "Publicar")]

    def __init__(self, parent):
        super().__init__(parent, bg=BG_DARK, highlightthickness=0, height=70)
        self._current = 0
        self._completed = set()
        self.bind("<Configure>", self._draw)

    def set_step(self, idx, completed=None):
        self._current = idx
        if completed is not None:
            self._completed = set(completed)
        self._draw()

    def complete_step(self, idx):
        self._completed.add(idx)
        self._draw()

    def reset(self):
        self._current = 0
        self._completed = set()
        self._draw()

    def _draw(self, e=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20:
            return
        n = len(self.STEPS)
        sw = w / n
        yc = h // 2 - 4

        # Líneas entre pasos
        for i in range(1, n):
            x1 = sw * (i - 1) + sw / 2 + 20
            x2 = sw * i + sw / 2 - 20
            color = ACCENT_CYAN if i <= self._current else BORDER_BRIGHT
            self.create_line(x1, yc, x2, yc, fill=color, width=2)

        # Círculos y etiquetas
        for i, (icon, label) in enumerate(self.STEPS):
            cx = sw * i + sw / 2
            r = 17
            if i in self._completed:
                fill, txt, tcol = ACCENT_GREEN, "✓", "white"
            elif i == self._current:
                fill, txt, tcol = ACCENT_CYAN, icon, "white"
            else:
                fill, txt, tcol = BORDER_BRIGHT, str(i + 1), FG_MUTED

            self.create_oval(cx - r, yc - r, cx + r, yc + r, fill=fill, outline=fill)
            self.create_text(cx, yc, text=txt, fill=tcol, font=(FONT_FAMILY, 10, "bold"))
            lcol = FG_PRIMARY if i == self._current else FG_SECONDARY
            weight = "bold" if i == self._current else ""
            self.create_text(cx, yc + r + 14, text=label, fill=lcol,
                             font=(FONT_FAMILY, 9, weight))


# ─── HTML renderer ──────────────────────────────────────────────
class HTMLRenderer(HTMLParser):
    def __init__(self, text_widget: tk.Text):
        super().__init__()
        self.tw = text_widget
        self._tag_stack = []

    def render(self, html: str):
        self.tw.configure(state=tk.NORMAL)
        self.tw.delete("1.0", tk.END)
        self.feed(html)
        self.tw.configure(state=tk.DISABLED)

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "p":
            self.tw.insert(tk.END, "\n\n")
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        tags = tuple(self._tag_stack)
        tk_tags = []
        if "strong" in tags or "b" in tags:
            tk_tags.append("bold")
        if "em" in tags or "i" in tags:
            tk_tags.append("italic")
        self.tw.insert(tk.END, data, tuple(tk_tags) if tk_tags else ())


# ─── Diálogo de configuración ───────────────────────────────────
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.title("Configuración")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.grab_set()
        _center_on_parent(self, parent, 900, 700)
        self._on_save = on_save

        self.settings = _load_settings()
        try:
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                self.prompts = json.load(f)
        except Exception:
            self.prompts = {}

        # Header
        hdr = tk.Frame(self, bg=BG_HEADER, height=50)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙  CONFIGURACIÓN", bg=BG_HEADER, fg="white",
                 font=(FONT_FAMILY, 14, "bold")).pack(anchor=tk.W, padx=16, pady=10)

        # Notebook
        s = ttk.Style(self)
        s.configure("Dark.TNotebook", background=BG_DARK, borderwidth=0)
        s.configure("Dark.TNotebook.Tab", background=BG_CARD, foreground=FG_PRIMARY,
                     font=(FONT_FAMILY, 10, "bold"), padding=[14, 8])
        s.map("Dark.TNotebook.Tab",
              background=[("selected", ACCENT_BLUE)], foreground=[("selected", "white")])

        nb = ttk.Notebook(self, style="Dark.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # ── Tab General ──
        tab_gen = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_gen, text="📂  General")

        tk.Label(tab_gen, text="Carpeta de vigilancia (watcher):", bg=BG_DARK, fg=FG_SECONDARY,
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(16, 4))
        folder_row = tk.Frame(tab_gen, bg=BG_DARK)
        folder_row.pack(fill=tk.X, padx=12)
        self.entry_folder = tk.Entry(
            folder_row, bg=BG_INPUT, fg=FG_PRIMARY, font=(FONT_FAMILY, 10),
            insertbackground=ACCENT_BLUE, relief=tk.FLAT, highlightthickness=1,
            highlightbackground=BORDER_BRIGHT, highlightcolor=ACCENT_CYAN,
        )
        self.entry_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_folder.insert(0, self.settings.get("watch_folder", ""))
        tk.Button(folder_row, text="📁", bg=BG_CARD, fg=FG_PRIMARY,
                  font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2",
                  command=self._browse_folder).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(tab_gen, text="Los archivos MP3 que aparezcan en esta carpeta serán\n"
                 "procesados automáticamente cuando el watcher esté activo.",
                 bg=BG_DARK, fg=FG_MUTED, font=(FONT_FAMILY, 8),
                 justify=tk.LEFT).pack(anchor=tk.W, padx=12, pady=(4, 0))

        tk.Frame(tab_gen, bg=BG_DARK, height=24).pack()

        # Papelera
        trash_card = tk.Frame(tab_gen, bg=BG_CARD)
        trash_card.pack(fill=tk.X, padx=12, pady=8)
        tk.Label(trash_card, text="🗑  Papelera", bg=BG_CARD, fg=FG_PRIMARY,
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(trash_card, text="Elimina permanentemente los archivos de audio ya procesados.",
                 bg=BG_CARD, fg=FG_SECONDARY, font=(FONT_FAMILY, 8)
                 ).pack(anchor=tk.W, padx=14, pady=(0, 8))
        tk.Button(trash_card, text="🗑  Vaciar papelera", bg=ACCENT_RED, fg="white",
                  font=(FONT_FAMILY, 10, "bold"), relief=tk.FLAT, padx=16, pady=6,
                  cursor="hand2", command=self._vaciar_papelera
                  ).pack(anchor=tk.W, padx=14, pady=(0, 14))

        # ── Tabs de Prompts ──
        self.editors = {}
        tab_labels = {"redaccion": "✍️  Redacción", "verificacion": "🔍 Verificación"}
        for key in ["redaccion", "verificacion"]:
            tab = tk.Frame(nb, bg=BG_DARK)
            nb.add(tab, text=tab_labels[key])
            cfg = self.prompts.get(key, {})

            tk.Label(tab, text="Modelo:", bg=BG_DARK, fg=FG_SECONDARY,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 2))
            entry_model = tk.Entry(
                tab, bg=BG_INPUT, fg=FG_PRIMARY, font=(FONT_FAMILY, 10),
                insertbackground=ACCENT_BLUE, relief=tk.FLAT, highlightthickness=1,
                highlightbackground=BORDER_BRIGHT, highlightcolor=ACCENT_CYAN,
            )
            entry_model.pack(fill=tk.X, padx=12, pady=(0, 8))
            entry_model.insert(0, cfg.get("modelo", ""))

            tk.Label(tab, text="System Prompt:", bg=BG_DARK, fg=FG_SECONDARY,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(4, 2))
            txt_sys = ScrolledText(
                tab, bg=BG_INPUT, fg=FG_PRIMARY, font=(FONT_FAMILY, 9),
                insertbackground=ACCENT_BLUE, relief=tk.FLAT, height=14,
                highlightthickness=1, highlightbackground=BORDER_BRIGHT,
                highlightcolor=ACCENT_CYAN, wrap=tk.WORD,
            )
            txt_sys.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
            txt_sys.insert("1.0", cfg.get("system_prompt", ""))

            tk.Label(tab, text="User Prompt Template:", bg=BG_DARK, fg=FG_SECONDARY,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(4, 2))
            txt_usr = ScrolledText(
                tab, bg=BG_INPUT, fg=FG_PRIMARY, font=(FONT_FAMILY, 9),
                insertbackground=ACCENT_BLUE, relief=tk.FLAT, height=5,
                highlightthickness=1, highlightbackground=BORDER_BRIGHT,
                highlightcolor=ACCENT_CYAN, wrap=tk.WORD,
            )
            txt_usr.pack(fill=tk.X, padx=12, pady=(0, 8))
            txt_usr.insert("1.0", cfg.get("user_prompt_template", ""))

            self.editors[key] = (entry_model, txt_sys, txt_usr)

        # Barra inferior
        btn_bar = tk.Frame(self, bg=BG_CARD, height=55)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_bar.pack_propagate(False)
        tk.Button(btn_bar, text="💾  Guardar", bg=ACCENT_GREEN, fg="white",
                  font=(FONT_FAMILY, 11, "bold"), relief=tk.FLAT, padx=20, pady=6,
                  cursor="hand2", command=self._save).pack(side=tk.LEFT, padx=12, pady=10)
        tk.Button(btn_bar, text="Cancelar", bg=FG_MUTED, fg="white",
                  font=(FONT_FAMILY, 10), relief=tk.FLAT, padx=16, pady=6,
                  cursor="hand2", command=self.destroy).pack(side=tk.LEFT)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta de vigilancia")
        if folder:
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)

    def _vaciar_papelera(self):
        folder = self.entry_folder.get().strip()
        if not folder:
            messagebox.showwarning("Aviso", "No hay carpeta configurada.", parent=self)
            return
        trash = os.path.join(folder, "papelera")
        if not os.path.isdir(trash):
            messagebox.showinfo("Info", "La papelera está vacía.", parent=self)
            return
        files = os.listdir(trash)
        if not files:
            messagebox.showinfo("Info", "La papelera está vacía.", parent=self)
            return
        if messagebox.askyesno("Confirmar",
                               f"¿Eliminar permanentemente {len(files)} archivo(s)?",
                               parent=self):
            try:
                shutil.rmtree(trash)
                os.makedirs(trash, exist_ok=True)
                messagebox.showinfo("Hecho", "Papelera vaciada.", parent=self)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=self)

    def _save(self):
        self.settings["watch_folder"] = self.entry_folder.get().strip()
        _save_settings(self.settings)

        for key, (em, ts, tu) in self.editors.items():
            if key not in self.prompts:
                self.prompts[key] = {}
            self.prompts[key]["modelo"] = em.get().strip()
            self.prompts[key]["system_prompt"] = ts.get("1.0", tk.END).strip()
            self.prompts[key]["user_prompt_template"] = tu.get("1.0", tk.END).strip()
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.prompts, f, ensure_ascii=False, indent=4)

        if self._on_save:
            self._on_save()
        self.destroy()


# ─── Diálogo de verificación ────────────────────────────────────
class VerificationDialog(tk.Toplevel):
    def __init__(self, parent, correcciones, texto_corregido, fuentes, aviso,
                 callback_aplicar, texto_original=None):
        super().__init__(parent)
        self.title("Verificación periodística")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.grab_set()
        _center_on_parent(self, parent, 860, 720)

        self.texto_corregido = texto_corregido
        self.texto_original = texto_original or {}
        self.callback_aplicar = callback_aplicar
        self.checks = []

        hdr = tk.Frame(self, bg=BG_HEADER, height=55)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🔍  VERIFICACIÓN CON IA + BÚSQUEDA WEB", bg=BG_HEADER,
                 fg="white", font=(FONT_FAMILY, 13, "bold")
                 ).pack(anchor=tk.W, padx=16, pady=12)

        main = tk.Frame(self, bg=BG_DARK)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        if aviso:
            af = tk.Frame(main, bg=BG_CARD)
            af.pack(fill=tk.X, pady=(0, 10))
            tk.Label(af, text=aviso, bg=BG_CARD, fg=ACCENT_YELLOW,
                     font=(FONT_FAMILY, 9, "italic"), wraplength=790, justify=tk.LEFT
                     ).pack(anchor=tk.W, padx=14, pady=10)

        canvas_f = tk.Frame(main, bg=BG_DARK)
        canvas_f.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        canvas = tk.Canvas(canvas_f, bg=BG_DARK, highlightthickness=0)
        sb = tk.Scrollbar(canvas_f, orient="vertical", command=canvas.yview)
        self.items_frame = tk.Frame(canvas, bg=BG_DARK)
        self.items_frame.bind("<Configure>",
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for corr in correcciones:
            var = tk.BooleanVar(value=True)
            self.checks.append((var, corr))
            num = corr.get("numero", "")
            card = tk.Frame(self.items_frame, bg=BG_CARD)
            card.pack(fill=tk.X, pady=5, padx=2)
            row = tk.Frame(card, bg=BG_CARD)
            row.pack(fill=tk.X, padx=12, pady=(10, 4))
            tk.Checkbutton(row, variable=var, bg=BG_CARD, activebackground=BG_CARD,
                           selectcolor=ACCENT_BLUE).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(row, text=f"Corrección #{num}", bg=BG_CARD, fg=ACCENT_BLUE,
                     font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)
            body = tk.Frame(card, bg=BG_CARD)
            body.pack(fill=tk.X, padx=36, pady=(0, 10))
            tk.Label(body, text="❌ Original:", bg=BG_CARD, fg=ACCENT_RED,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W)
            tk.Label(body, text=corr.get("original", ""), bg=BG_CARD, fg=FG_PRIMARY,
                     font=(FONT_FAMILY, 9), wraplength=720, justify=tk.LEFT).pack(anchor=tk.W)
            tk.Label(body, text="✅ Corrección:", bg=BG_CARD, fg=ACCENT_GREEN,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, pady=(6, 0))
            tk.Label(body, text=corr.get("corregido", ""), bg=BG_CARD, fg=FG_PRIMARY,
                     font=(FONT_FAMILY, 9), wraplength=720, justify=tk.LEFT).pack(anchor=tk.W)
            expl = corr.get("explicacion", "")
            if expl:
                tk.Label(body, text=f"💡 {expl}", bg=BG_CARD, fg=FG_SECONDARY,
                         font=(FONT_FAMILY, 8, "italic"), wraplength=720
                         ).pack(anchor=tk.W, pady=(4, 0))
            fecha_ref = corr.get("fecha_referencia", "")
            if fecha_ref:
                tk.Label(body, text=f"📅 Fecha de la fuente: {fecha_ref}", bg=BG_CARD,
                         fg=ACCENT_GOLD, font=(FONT_FAMILY, 8),
                         ).pack(anchor=tk.W, pady=(2, 0))
            src = corr.get("fuente", "")
            if src:
                lbl = tk.Label(body, text=f"🔗 {src}", bg=BG_CARD, fg=ACCENT_CYAN,
                               font=(FONT_FAMILY, 8, "underline"), cursor="hand2", wraplength=720)
                lbl.pack(anchor=tk.W, pady=(2, 0))
                lbl.bind("<Button-1>", lambda e, u=src: webbrowser.open(u))

        if fuentes:
            sf = tk.Frame(main, bg=BG_CARD)
            sf.pack(fill=tk.X, pady=(8, 0))
            tk.Label(sf, text="📚 Fuentes consultadas:", bg=BG_CARD, fg=FG_SECONDARY,
                     font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, padx=14, pady=(10, 4))
            for url in fuentes:
                l = tk.Label(sf, text=f"  🔗 {url}", bg=BG_CARD, fg=ACCENT_CYAN,
                             font=(FONT_FAMILY, 8, "underline"), cursor="hand2")
                l.pack(anchor=tk.W, padx=14, pady=1)
                l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        btns = tk.Frame(self, bg=BG_CARD, height=55)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        btns.pack_propagate(False)
        tk.Button(btns, text="✓  Aplicar correcciones", bg=ACCENT_GREEN, fg="white",
                  font=(FONT_FAMILY, 11, "bold"), relief=tk.FLAT, padx=18, pady=7,
                  cursor="hand2", command=self._aplicar).pack(side=tk.LEFT, padx=12, pady=10)
        tk.Button(btns, text="✕  Cancelar", bg=FG_MUTED, fg="white",
                  font=(FONT_FAMILY, 10), relief=tk.FLAT, padx=14, pady=7,
                  cursor="hand2", command=self.destroy).pack(side=tk.LEFT)

    def _aplicar(self):
        omitidos = [str(c["numero"]) for v, c in self.checks if not v.get()]
        aplicados = [(v, c) for v, c in self.checks if v.get()]
        if omitidos:
            dlg = tk.Toplevel(self)
            dlg.title("Confirmar")
            dlg.configure(bg=BG_DARK)
            dlg.grab_set()
            dlg.resizable(False, False)
            _center_on_parent(dlg, self, 440, 180)
            tk.Label(
                dlg,
                text=f"Se omitirán las correcciones: #{', #'.join(omitidos)}.\n"
                     "Esas partes quedarán como estaban en el borrador.",
                bg=BG_DARK, fg=FG_PRIMARY, font=(FONT_FAMILY, 10),
                wraplength=400, justify=tk.CENTER,
            ).pack(pady=24)
            row = tk.Frame(dlg, bg=BG_DARK)
            row.pack()
            result = [False]

            def ok():
                result[0] = True
                dlg.destroy()

            def cancel():
                dlg.destroy()

            tk.Button(row, text="Continuar", bg=ACCENT_GREEN, fg="white",
                      font=(FONT_FAMILY, 10, "bold"), relief=tk.FLAT, padx=16, pady=6,
                      cursor="hand2", command=ok).pack(side=tk.LEFT, padx=8)
            tk.Button(row, text="Volver", bg=FG_MUTED, fg="white",
                      font=(FONT_FAMILY, 10), relief=tk.FLAT, padx=16, pady=6,
                      cursor="hand2", command=cancel).pack(side=tk.LEFT)
            dlg.wait_window()
            if not result[0]:
                return

        # Si hay correcciones omitidas, aplicar solo las seleccionadas
        if omitidos and self.texto_original:
            resultado = {
                "titulo": self.texto_original.get("titulo", ""),
                "entradilla": self.texto_original.get("entradilla", ""),
                "contenido": self.texto_original.get("contenido", ""),
                "etiquetas": list(self.texto_original.get("etiquetas", [])),
            }
            for _, corr in aplicados:
                orig = corr.get("original", "")
                fixed = corr.get("corregido", "")
                if not orig or not fixed:
                    continue
                for campo in ["titulo", "entradilla", "contenido"]:
                    if orig in resultado[campo]:
                        resultado[campo] = resultado[campo].replace(orig, fixed, 1)
                        break
            self.callback_aplicar(resultado)
        else:
            self.callback_aplicar(self.texto_corregido)
        self.destroy()


# ─── MP3 file handler (watchdog) ────────────────────────────────


# ─── Aplicación principal ───────────────────────────────────────
class PublicadorApp(tk.Tk):
    STEP_AUDIO   = 0
    STEP_PROCESS = 1
    STEP_EDIT    = 2
    STEP_PUBLISH = 3

    def __init__(self):
        super().__init__()
        self.title("HTV · Publicador Inteligente")
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.configure(bg=BG_DARK)

        self._setup_styles()

        self.archivo_audio = None
        self.original_filename = None
        self._html_contenido = ""
        self._toast_job = None
        self._toast_frame = None
        self._watcher_active = False
        self._observer = None
        self._processing = False
        self._mp3_queue = queue.Queue()
        self._auto_publish_pending = False
        self._progress_anim_id = None

        self._build_ui()
        self._show_step(self.STEP_AUDIO)

    # ── Estilos ttk ──────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TButton", background=BG_CARD, foreground=FG_PRIMARY,
                     font=(FONT_FAMILY, 10, "bold"), padding=(12, 10), borderwidth=0)
        s.map("TButton", background=[("active", "#223042"), ("disabled", "#21262d")],
              foreground=[("disabled", FG_MUTED)])
        s.configure("Blue.TButton", background=ACCENT_BLUE, foreground="white",
                     font=(FONT_FAMILY, 10, "bold"), padding=(14, 11))
        s.map("Blue.TButton", background=[("active", "#1f6feb"), ("disabled", "#21262d")])
        s.configure("Purple.TButton", background=ACCENT_PURPLE, foreground="white",
                     font=(FONT_FAMILY, 10, "bold"), padding=(14, 11))
        s.map("Purple.TButton", background=[("active", "#a371f7"), ("disabled", "#21262d")])
        s.configure("Green.TButton", background=ACCENT_GREEN, foreground="white",
                     font=(FONT_FAMILY, 12, "bold"), padding=(16, 12))
        s.map("Green.TButton", background=[("active", "#238636"), ("disabled", "#21262d")])
        s.configure("Red.TButton", background=ACCENT_RED, foreground="white",
                     font=(FONT_FAMILY, 10, "bold"), padding=(12, 10))
        s.map("Red.TButton", background=[("active", "#da3633"), ("disabled", "#21262d")])

    def _init_services(self):
        try:
            self.transcription_svr = TranscriptionService()
            self.writer_svr = WriterService()
            self.publisher_svr = PublisherService()
            self.verification_svr = VerificationService()
        except Exception as e:
            self.after(200, lambda err=e: self._toast(f"Error de configuración: {err}", kind="error"))

    # ── Toast ────────────────────────────────────────────────────
    def _toast(self, message, kind="info", duration=4500):
        colors = {
            "info":    (ACCENT_CYAN,   "#0d2233"),
            "success": (ACCENT_GREEN,  "#0d1f0f"),
            "error":   (ACCENT_RED,    "#1f0d0d"),
            "warning": (ACCENT_YELLOW, "#1f1a0d"),
        }
        bc, bgc = colors.get(kind, colors["info"])
        if self._toast_frame:
            try:
                self._toast_frame.destroy()
            except Exception:
                pass
        if self._toast_job:
            self.after_cancel(self._toast_job)
            self._toast_job = None

        toast = tk.Frame(self, bg=bc)
        toast.place(relx=1.0, rely=1.0, x=-16, y=-16, anchor="se")
        inner = tk.Frame(toast, bg=bgc)
        inner.pack(padx=2, pady=2, fill=tk.BOTH, expand=True)
        icons = {"info": "ℹ", "success": "✓", "error": "✕", "warning": "⚠"}
        tk.Label(inner, text=icons.get(kind, "ℹ"), bg=bgc, fg=bc,
                 font=(FONT_FAMILY, 14, "bold")).pack(side=tk.LEFT, padx=(14, 8), pady=12)
        tk.Label(inner, text=message, bg=bgc, fg=FG_PRIMARY,
                 font=(FONT_FAMILY, 10), wraplength=340, justify=tk.LEFT
                 ).pack(side=tk.LEFT, pady=12, padx=(0, 16))
        self._toast_frame = toast
        self._toast_job = self.after(duration, self._dismiss_toast)

    def _dismiss_toast(self):
        if self._toast_frame:
            try:
                self._toast_frame.destroy()
            except Exception:
                pass
            self._toast_frame = None
        self._toast_job = None

    # ── Status LED ───────────────────────────────────────────────
    def _set_status(self, text, color=None):
        self.lbl_status.config(text=text)
        self.led.config(fg=color or FG_MUTED)

    # ══════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=BG_HEADER)
        hdr.pack(fill=tk.X)
        tk.Frame(self, bg=ACCENT_CYAN, height=2).pack(fill=tk.X)

        hdr_inner = tk.Frame(hdr, bg=BG_HEADER)
        hdr_inner.pack(fill=tk.BOTH, expand=True, padx=20)

        left = tk.Frame(hdr_inner, bg=BG_HEADER)
        left.pack(side=tk.LEFT, pady=10)
        tk.Label(left, text="📺  PUBLICADOR WEB HTV", bg=BG_HEADER, fg="white",
                 font=(FONT_FAMILY, 15, "bold")).pack(anchor=tk.W)
        tk.Label(left, text="Redacción automática · Verificación · Publicación",
                 bg=BG_HEADER, fg=ACCENT_CYAN, font=(FONT_FAMILY, 8)).pack(anchor=tk.W)

        right = tk.Frame(hdr_inner, bg=BG_HEADER)
        right.pack(side=tk.RIGHT, pady=10)

        # Watcher toggle
        watcher_row = tk.Frame(right, bg=BG_HEADER)
        watcher_row.pack(side=tk.LEFT, padx=(0, 14))
        tk.Label(watcher_row, text="Auto", bg=BG_HEADER, fg=FG_SECONDARY,
                 font=(FONT_FAMILY, 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.toggle_watcher = ToggleSwitch(
            watcher_row, command=self._on_toggle_watcher,
            initial=False, bg_on=ACCENT_CYAN, bg_off=FG_MUTED,
        )
        self.toggle_watcher.pack(side=tk.LEFT)

        tk.Button(right, text="⚙", bg=BG_CARD_SOFT, fg=FG_SECONDARY,
                  font=(FONT_FAMILY, 14), relief=tk.FLAT, borderwidth=0,
                  cursor="hand2", activebackground="#252f3a", activeforeground=ACCENT_CYAN,
                  command=self._open_settings).pack(side=tk.LEFT, padx=4)

        # ── Step indicator ──
        self.step_indicator = StepIndicator(self)
        self.step_indicator.pack(fill=tk.X, padx=20, pady=(6, 0))

        # ── Content area ──
        self.content_area = tk.Frame(self, bg=BG_DARK)
        self.content_area.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 6))

        self.step_frames = []
        for builder in [self._build_step_audio, self._build_step_process,
                        self._build_step_edit, self._build_step_publish]:
            f = tk.Frame(self.content_area, bg=BG_DARK)
            builder(f)
            self.step_frames.append(f)

        # ── Status bar ──
        sbar = tk.Frame(self, bg="#0a0a0a", height=30)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)
        sbar.pack_propagate(False)
        self.led = tk.Label(sbar, text="●", fg=FG_MUTED, bg="#0a0a0a",
                            font=(FONT_FAMILY, 10))
        self.led.pack(side=tk.LEFT, padx=(14, 4))
        self.lbl_status = tk.Label(sbar, text="Esperando acción...",
                                   bg="#0a0a0a", fg=FG_SECONDARY,
                                   font=(FONT_FAMILY, 9, "bold"))
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_watcher_info = tk.Label(sbar, text="", bg="#0a0a0a", fg=FG_MUTED,
                                         font=(FONT_FAMILY, 8))
        self.lbl_watcher_info.pack(side=tk.RIGHT, padx=(0, 14))

    # ── Step builders ────────────────────────────────────────────
    def _build_step_audio(self, parent):
        """Paso 1 — Selección de audio / Esperando watcher."""
        center = tk.Frame(parent, bg=BG_DARK)
        center.place(relx=0.5, rely=0.42, anchor="center")

        # Vista manual
        self.audio_manual_frame = tk.Frame(center, bg=BG_DARK)
        tk.Label(self.audio_manual_frame, text="🎙", bg=BG_DARK, fg=ACCENT_CYAN,
                 font=(FONT_FAMILY, 48)).pack(pady=(0, 6))
        tk.Label(self.audio_manual_frame, text="Seleccionar Audio", bg=BG_DARK,
                 fg=FG_PRIMARY, font=(FONT_FAMILY, 16, "bold")).pack()
        tk.Label(self.audio_manual_frame, text="Elige un archivo MP3, WAV, OGG o M4A",
                 bg=BG_DARK, fg=FG_SECONDARY, font=(FONT_FAMILY, 9)).pack(pady=(4, 20))
        self.btn_select = ttk.Button(self.audio_manual_frame, text="📂  Seleccionar archivo",
                                     style="Blue.TButton", command=self._seleccionar_audio)
        self.btn_select.pack(ipadx=20, ipady=4)
        self.lbl_file = tk.Label(self.audio_manual_frame, text="", bg=BG_DARK,
                                 fg=FG_SECONDARY, font=(FONT_FAMILY, 9, "italic"))
        self.lbl_file.pack(pady=(12, 0))

        # Vista watcher
        self.audio_watcher_frame = tk.Frame(center, bg=BG_DARK)
        tk.Label(self.audio_watcher_frame, text="👁", bg=BG_DARK, fg=ACCENT_CYAN,
                 font=(FONT_FAMILY, 48)).pack(pady=(0, 6))
        tk.Label(self.audio_watcher_frame, text="Vigilando carpeta…", bg=BG_DARK,
                 fg=FG_PRIMARY, font=(FONT_FAMILY, 16, "bold")).pack()
        self.lbl_watch_folder = tk.Label(self.audio_watcher_frame, text="", bg=BG_DARK,
                                         fg=ACCENT_CYAN, font=(FONT_FAMILY, 9))
        self.lbl_watch_folder.pack(pady=(8, 4))
        tk.Label(self.audio_watcher_frame, text="Esperando archivos MP3…",
                 bg=BG_DARK, fg=FG_SECONDARY, font=(FONT_FAMILY, 9, "italic")).pack()

        self.audio_manual_frame.pack()

    def _build_step_process(self, parent):
        """Paso 2 — Feedback de procesamiento."""
        center = tk.Frame(parent, bg=BG_DARK)
        center.place(relx=0.5, rely=0.42, anchor="center")

        self.lbl_proc_icon = tk.Label(center, text="⏳", bg=BG_DARK, fg=ACCENT_BLUE,
                                      font=(FONT_FAMILY, 48))
        self.lbl_proc_icon.pack(pady=(0, 6))
        self.lbl_proc_title = tk.Label(center, text="Procesando…", bg=BG_DARK,
                                       fg=FG_PRIMARY, font=(FONT_FAMILY, 16, "bold"))
        self.lbl_proc_title.pack()
        self.lbl_proc_detail = tk.Label(center, text="Transcribiendo y redactando con IA",
                                        bg=BG_DARK, fg=FG_SECONDARY, font=(FONT_FAMILY, 9))
        self.lbl_proc_detail.pack(pady=(8, 16))
        self.lbl_proc_file = tk.Label(center, text="", bg=BG_DARK, fg=ACCENT_CYAN,
                                      font=(FONT_FAMILY, 9, "italic"))
        self.lbl_proc_file.pack()

        self.progress_canvas = tk.Canvas(center, bg=BG_DARK, height=6,
                                         highlightthickness=0, width=320)
        self.progress_canvas.pack(pady=(16, 0))

    def _build_step_edit(self, parent):
        """Paso 3 — Editar y verificar la noticia."""
        # Canvas scrollable para el formulario largo
        self._edit_canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=self._edit_canvas.yview)
        sf = tk.Frame(self._edit_canvas, bg=BG_DARK)
        win = self._edit_canvas.create_window((0, 0), window=sf, anchor="nw")
        self._edit_canvas.bind("<Configure>",
                               lambda e: self._edit_canvas.itemconfig(win, width=e.width))
        sf.bind("<Configure>",
                lambda e: self._edit_canvas.configure(scrollregion=self._edit_canvas.bbox("all")))
        self._edit_canvas.configure(yscrollcommand=sb.set)
        self._edit_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        pad = tk.Frame(sf, bg=BG_DARK)
        pad.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Barra de título del paso
        title_row = tk.Frame(pad, bg=BG_DARK)
        title_row.pack(fill=tk.X, pady=(0, 14))
        tk.Label(title_row, text="📝  Editar Noticia", bg=BG_DARK, fg=FG_PRIMARY,
                 font=(FONT_FAMILY, 14, "bold")).pack(side=tk.LEFT)

        # Titular
        self._field_label(pad, "📌  Titular")
        self.txt_titulo = RoundedText(
            pad, text_height=2, radius=10, bg_fill=BG_INPUT,
            font=(FONT_FAMILY, 12, "bold"), fg=FG_PRIMARY,
            insertbackground=ACCENT_CYAN, wrap=tk.WORD,
            selectbackground="#2f81f7", selectforeground="white",
        )
        self.txt_titulo.pack(fill=tk.X, pady=(0, 14))

        # Cuerpo (vista previa)
        self._field_label(pad, "📰  Cuerpo de la Noticia")
        self.txt_preview = RoundedText(
            pad, text_height=12, radius=10, bg_fill="#0f1824",
            font=(FONT_FAMILY, 10), fg=FG_PRIMARY, wrap=tk.WORD,
            selectbackground="#2f81f7", selectforeground="white",
        )
        self.txt_preview.text.configure(state=tk.DISABLED, padx=12, pady=8)
        self.txt_preview.text.tag_configure("bold", font=(FONT_FAMILY, 10, "bold"),
                                            foreground=FG_PRIMARY)
        self.txt_preview.text.tag_configure("italic", font=(FONT_FAMILY, 10, "italic"),
                                            foreground=FG_SECONDARY)
        self.txt_preview.pack(fill=tk.X, pady=(0, 14))
        self.html_renderer = HTMLRenderer(self.txt_preview.text)

        # Entradilla
        self._field_label(pad, "💬  Entradilla  (excerpt en WordPress)")
        self.txt_entradilla = RoundedText(
            pad, text_height=2, radius=10, bg_fill=BG_INPUT,
            font=(FONT_FAMILY, 9, "italic"), fg=FG_SECONDARY,
            insertbackground=ACCENT_CYAN, wrap=tk.WORD,
            selectbackground="#2f81f7", selectforeground="white",
        )
        self.txt_entradilla.pack(fill=tk.X, pady=(0, 14))

        # Etiquetas
        self._field_label(pad, "🏷  Etiquetas (separadas por coma)")
        self.txt_etiquetas = RoundedText(
            pad, text_height=2, radius=10, bg_fill=BG_INPUT,
            font=(FONT_FAMILY, 9), fg=FG_PRIMARY,
            insertbackground=ACCENT_CYAN, wrap=tk.WORD,
            selectbackground="#2f81f7", selectforeground="white",
        )
        self.txt_etiquetas.pack(fill=tk.X, pady=(0, 20))

        # Botones de acción
        btn_row = tk.Frame(pad, bg=BG_DARK)
        btn_row.pack(fill=tk.X, pady=(0, 12))
        self.btn_verify = ttk.Button(btn_row, text="🔍  Verificar",
                                     style="Purple.TButton",
                                     command=self._iniciar_verificacion)
        self.btn_verify.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_publish = ttk.Button(btn_row, text="🚀  Publicar",
                                      style="Green.TButton", command=self._publicar)
        self.btn_publish.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="🗑  Limpiar", style="Red.TButton",
                   command=self._limpiar_todo).pack(side=tk.RIGHT)

    def _build_step_publish(self, parent):
        """Paso 4 — Resultado de publicación."""
        center = tk.Frame(parent, bg=BG_DARK)
        center.place(relx=0.5, rely=0.42, anchor="center")

        self.lbl_pub_icon = tk.Label(center, text="🚀", bg=BG_DARK, fg=ACCENT_BLUE,
                                     font=(FONT_FAMILY, 48))
        self.lbl_pub_icon.pack(pady=(0, 6))
        self.lbl_pub_title = tk.Label(center, text="Publicando…", bg=BG_DARK,
                                      fg=FG_PRIMARY, font=(FONT_FAMILY, 16, "bold"))
        self.lbl_pub_title.pack()
        self.lbl_pub_detail = tk.Label(center, text="", bg=BG_DARK, fg=FG_SECONDARY,
                                       font=(FONT_FAMILY, 10))
        self.lbl_pub_detail.pack(pady=(8, 16))
        self.lbl_pub_url = tk.Label(center, text="", bg=BG_DARK, fg=ACCENT_CYAN,
                                    font=(FONT_FAMILY, 9, "underline"), cursor="hand2")
        self.lbl_pub_url.pack(pady=(0, 20))
        self.lbl_pub_url.bind("<Button-1>", lambda e: (
            webbrowser.open(self.lbl_pub_url.cget("text"))
            if self.lbl_pub_url.cget("text") else None
        ))
        self.btn_new = ttk.Button(center, text="🔄  Nueva noticia",
                                  style="Blue.TButton", command=self._reset_flow)
        self.btn_new.pack(ipadx=20, ipady=4)

    # ══════════════════════════════════════════════════════════════
    #  NAVEGACIÓN DE PASOS
    # ══════════════════════════════════════════════════════════════
    def _show_step(self, idx):
        for f in self.step_frames:
            f.pack_forget()
        self.step_frames[idx].pack(fill=tk.BOTH, expand=True)
        completed = list(range(idx))
        self.step_indicator.set_step(idx, completed)

        # Bind mousewheel solo para el paso de edición
        if idx == self.STEP_EDIT:
            self.bind_all("<MouseWheel>", self._on_edit_scroll)
        else:
            try:
                self.unbind_all("<MouseWheel>")
            except Exception:
                pass

    def _on_edit_scroll(self, event):
        self._edit_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _reset_flow(self):
        """Vuelve al paso 1 y limpia estado interno."""
        self.archivo_audio = None
        self.original_filename = None
        self._html_contenido = ""
        self._processing = False
        self._auto_publish_pending = False
        self.step_indicator.reset()

        # Limpiar campos
        self.txt_titulo.text.delete("1.0", tk.END)
        self.txt_entradilla.text.delete("1.0", tk.END)
        self._set_html_contenido("")
        self.txt_etiquetas.text.delete("1.0", tk.END)
        self.lbl_file.config(text="")

        # Resetear vistas de pasos 2 y 4
        self.lbl_proc_icon.config(text="⏳", fg=ACCENT_BLUE)
        self.lbl_proc_title.config(text="Procesando…")
        self.lbl_proc_detail.config(text="Transcribiendo y redactando con IA")
        self.lbl_proc_file.config(text="")
        self.btn_verify.config(state=tk.NORMAL)
        self.btn_publish.config(state=tk.NORMAL)

        self._show_step(self.STEP_AUDIO)
        self._update_audio_view()
        self._set_status("Esperando acción…", FG_MUTED)

        # Si hay cola, procesar siguiente
        if self._watcher_active and not self._mp3_queue.empty():
            next_path = self._mp3_queue.get()
            self.after(800, lambda: self._on_mp3_detected(next_path))

    def _update_audio_view(self):
        if self._watcher_active:
            self.audio_manual_frame.pack_forget()
            self.audio_watcher_frame.pack()
            settings = _load_settings()
            folder = settings.get("watch_folder", "")
            self.lbl_watch_folder.config(
                text=f"📂 {folder}" if folder else "⚠ Carpeta no configurada"
            )
        else:
            self.audio_watcher_frame.pack_forget()
            self.audio_manual_frame.pack()

    # ══════════════════════════════════════════════════════════════
    #  WATCHER
    # ══════════════════════════════════════════════════════════════
    def _on_toggle_watcher(self, is_on):
        if is_on:
            self._start_watcher()
        else:
            self._stop_watcher()

    def _start_watcher(self):
        if not HAS_WATCHDOG:
            self._toast("Instala 'watchdog': pip install watchdog", kind="error")
            self.toggle_watcher.set(False)
            return
        settings = _load_settings()
        folder = settings.get("watch_folder", "")
        if not folder or not os.path.isdir(folder):
            self._toast("Configura la carpeta de vigilancia en ⚙.", kind="warning")
            self.toggle_watcher.set(False)
            return

        handler = Mp3Handler(lambda path: self.after(0, self._on_mp3_detected, path))  # type: ignore[name-defined]
        self._observer = Observer()  # type: ignore[name-defined]
        self._observer.schedule(handler, folder, recursive=False)
        self._observer.start()
        self._watcher_active = True
        self._update_audio_view()
        self.lbl_watcher_info.config(text="👁 Watcher activo", fg=ACCENT_GREEN)
        self._set_status(f"Vigilando: {folder}", ACCENT_CYAN)
        self._toast("Watcher activado.", kind="info")
        if self.step_indicator._current == self.STEP_AUDIO:
            self._show_step(self.STEP_AUDIO)

        # ── Procesar archivos que ya estaban en la carpeta ──────────
        _EXTS = {".mp4", ".mp3", ".wav", ".m4a", ".ogg",
                 ".flac", ".webm", ".mpeg", ".mpg", ".mov"}
        existing = sorted(
            (
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in _EXTS
                and os.path.isfile(os.path.join(folder, f))
            ),
            key=os.path.getmtime,
        )
        for filepath in existing:
            handler._processed.add(filepath)     # evitar doble disparo del observer
            self.after(0, self._on_mp3_detected, filepath)
        if existing:
            self._toast(
                f"{len(existing)} archivo(s) pendiente(s) encontrado(s) en la carpeta, añadido(s) a la cola.",
                kind="info",
            )

    def _stop_watcher(self):
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
            self._observer = None
        self._watcher_active = False
        self._update_audio_view()
        self.lbl_watcher_info.config(text="", fg=FG_MUTED)
        self._set_status("Modo manual.", FG_MUTED)
        self._toast("Watcher desactivado.", kind="info")

    def _on_mp3_detected(self, path):
        """El watcher detectó un MP3 nuevo."""
        if self._processing:
            self._mp3_queue.put(path)
            self._toast(f"En cola: {os.path.basename(path)}", kind="info")
            return
        self._processing = True
        self.archivo_audio = path
        self.original_filename = os.path.basename(path)
        self._auto_publish_pending = True
        self._set_status(f"Detectado: {self.original_filename}", ACCENT_CYAN)
        self._toast(f"MP3 detectado: {self.original_filename}", kind="info")

        self._show_step(self.STEP_PROCESS)
        self.lbl_proc_file.config(text=f"📁 {self.original_filename}")
        self._start_progress_anim()
        threading.Thread(target=self._hilo_procesamiento, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    #  PASO 1 — Selección manual de audio
    # ══════════════════════════════════════════════════════════════
    def _seleccionar_audio(self):
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo de audio",
            filetypes=(("Vídeo / Audio", "*.mp4 *.mp3 *.wav *.m4a *.ogg *.flac *.webm *.mpeg *.mpg *.mov"), ("Todos", "*.*")),
        )
        if not filepath:
            return
        self.archivo_audio = filepath
        self.original_filename = os.path.basename(filepath)
        self.lbl_file.config(text=f"📁  {self.original_filename}", fg=ACCENT_GREEN)
        self._set_status(f"Archivo: {self.original_filename}", ACCENT_GREEN)
        self._auto_publish_pending = False

        # Avanzar a paso 2 (procesar)
        self._processing = True
        self._show_step(self.STEP_PROCESS)
        self.lbl_proc_file.config(text=f"📁 {self.original_filename}")
        self._start_progress_anim()
        threading.Thread(target=self._hilo_procesamiento, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    #  PASO 2 — Procesamiento (transcripción + redacción)
    # ══════════════════════════════════════════════════════════════
    def _start_progress_anim(self):
        self._progress_pos = 0
        self._animate_progress()

    def _animate_progress(self):
        c = self.progress_canvas
        c.delete("all")
        w = 320
        _rounded_rect(c, 0, 0, w, 6, 3, fill=BORDER_BRIGHT, outline=BORDER_BRIGHT)
        bar_w = 80
        x = self._progress_pos % (w + bar_w) - bar_w
        _rounded_rect(c, max(0, x), 0, min(w, x + bar_w), 6, 3,
                      fill=ACCENT_CYAN, outline=ACCENT_CYAN)
        self._progress_pos += 3
        self._progress_anim_id = self.after(30, self._animate_progress)

    def _stop_progress_anim(self):
        if self._progress_anim_id:
            self.after_cancel(self._progress_anim_id)
            self._progress_anim_id = None

    def _hilo_procesamiento(self):
        try:
            self.after(0, lambda: self.lbl_proc_detail.config(
                text="Transcribiendo audio con IA…"))
            texto, motor = self.transcription_svr.transcribe(self.archivo_audio)

            self.after(0, lambda: self.lbl_proc_detail.config(
                text="Redactando noticia con IA…"))
            nombre_base, _ = os.path.splitext(self.original_filename or "")
            video_filename = f"{nombre_base}.mp4"
            noticia = self.writer_svr.write_news(texto, video_filename)

            self.after(0, self._procesamiento_ok, noticia)
        except Exception as e:
            self.after(0, self._procesamiento_error, str(e))

    def _procesamiento_ok(self, noticia):
        self._stop_progress_anim()
        self._fill_draft(noticia)
        self._set_status("Borrador generado.", ACCENT_GREEN)
        self._toast("Borrador generado correctamente.", kind="success")

        self._show_step(self.STEP_EDIT)

        if self._auto_publish_pending:
            # Modo automático: verificar y luego publicar
            self.after(400, lambda: self._iniciar_verificacion(auto_publish=True))

    def _procesamiento_error(self, msg):
        self._stop_progress_anim()
        self._processing = False
        self._auto_publish_pending = False
        self.lbl_proc_icon.config(text="❌", fg=ACCENT_RED)
        self.lbl_proc_title.config(text="Error en procesamiento")
        self.lbl_proc_detail.config(text=msg)
        self._set_status("Error.", ACCENT_RED)
        self._toast(msg, kind="error", duration=8000)
        self.after(5000, self._reset_flow)

    def _fill_draft(self, noticia):
        self.txt_titulo.text.delete("1.0", tk.END)
        self.txt_titulo.text.insert(tk.END, noticia.get("titulo", ""))
        self.txt_entradilla.text.delete("1.0", tk.END)
        self.txt_entradilla.text.insert(tk.END, noticia.get("entradilla", ""))
        self._set_html_contenido(noticia.get("contenido", ""))
        self.txt_etiquetas.text.delete("1.0", tk.END)
        self.txt_etiquetas.text.insert(tk.END, ", ".join(noticia.get("etiquetas", [])))

    def _set_html_contenido(self, html):
        self._html_contenido = html
        self.html_renderer.render(html)

    # ══════════════════════════════════════════════════════════════
    #  PASO 3 — Verificación
    # ══════════════════════════════════════════════════════════════
    def _iniciar_verificacion(self, auto_publish=False):
        self.btn_verify.config(state=tk.DISABLED)
        self.btn_publish.config(state=tk.DISABLED)
        self._set_status("Verificando con IA y búsqueda web…", ACCENT_PURPLE)
        threading.Thread(target=self._hilo_verificacion,
                         args=(auto_publish,), daemon=True).start()

    def _hilo_verificacion(self, auto_publish=False):
        try:
            news_data = {
                "titulo": self.txt_titulo.text.get("1.0", tk.END).strip(),
                "entradilla": self.txt_entradilla.text.get("1.0", tk.END).strip(),
                "contenido": self._html_contenido,
                "etiquetas": [t.strip() for t in
                              self.txt_etiquetas.text.get("1.0", tk.END).split(",")
                              if t.strip()],
            }
            resultado = self.verification_svr.verify(news_data)
            self.after(0, self._mostrar_verificacion, resultado, auto_publish)
        except Exception as e:
            self.after(0, self._verificacion_error, str(e))

    def _mostrar_verificacion(self, resultado, auto_publish=False):
        self.btn_verify.config(state=tk.NORMAL)
        self.btn_publish.config(state=tk.NORMAL)
        correcciones = resultado.get("correcciones", [])
        texto_corregido = resultado.get("texto_corregido", {})
        fuentes = resultado.get("fuentes_consultadas", [])
        aviso = resultado.get("aviso", "")

        if not correcciones:
            self._set_status("Sin correcciones necesarias.", ACCENT_GREEN)
            self._toast("Verificación completada. Sin correcciones.", kind="success")
            if auto_publish:
                self.after(600, self._publicar)
            return

        texto_original = {
            "titulo": self.txt_titulo.text.get("1.0", tk.END).strip(),
            "entradilla": self.txt_entradilla.text.get("1.0", tk.END).strip(),
            "contenido": self._html_contenido,
            "etiquetas": [t.strip() for t in
                          self.txt_etiquetas.text.get("1.0", tk.END).split(",")
                          if t.strip()],
        }
        VerificationDialog(
            self, correcciones, texto_corregido, fuentes, aviso,
            lambda tc: self._aplicar_correcciones(tc, auto_publish),
            texto_original=texto_original,
        )
        self._set_status("Revisando correcciones…", ACCENT_PURPLE)

    def _verificacion_error(self, msg):
        self.btn_verify.config(state=tk.NORMAL)
        self.btn_publish.config(state=tk.NORMAL)
        self._set_status("Error en verificación.", ACCENT_RED)
        self._toast(msg, kind="error", duration=8000)
        self._auto_publish_pending = False

    def _aplicar_correcciones(self, texto_corregido, auto_publish=False):
        if texto_corregido.get("titulo"):
            self.txt_titulo.text.delete("1.0", tk.END)
            self.txt_titulo.text.insert(tk.END, texto_corregido["titulo"])
        if texto_corregido.get("entradilla"):
            self.txt_entradilla.text.delete("1.0", tk.END)
            self.txt_entradilla.text.insert(tk.END, texto_corregido["entradilla"])
        if texto_corregido.get("contenido"):
            self._set_html_contenido(texto_corregido["contenido"])
        if texto_corregido.get("etiquetas"):
            self.txt_etiquetas.text.delete("1.0", tk.END)
            self.txt_etiquetas.text.insert(tk.END, ", ".join(texto_corregido["etiquetas"]))
        self._set_status("Correcciones aplicadas.", ACCENT_GREEN)
        self._toast("Correcciones aplicadas al borrador.", kind="success")

        if auto_publish:
            self.after(800, self._publicar)

    # ══════════════════════════════════════════════════════════════
    #  PASO 4 — Publicar
    # ══════════════════════════════════════════════════════════════
    def _publicar(self):
        self._show_step(self.STEP_PUBLISH)
        self.lbl_pub_icon.config(text="🚀", fg=ACCENT_BLUE)
        self.lbl_pub_title.config(text="Publicando…")
        self.lbl_pub_detail.config(text="Enviando artículo a WordPress…")
        self.lbl_pub_url.config(text="")
        self.btn_new.pack_forget()
        self._set_status("Publicando…", ACCENT_BLUE)

        news_data = {
            "titulo": self.txt_titulo.text.get("1.0", tk.END).strip(),
            "entradilla": self.txt_entradilla.text.get("1.0", tk.END).strip(),
            "contenido": self._html_contenido,
            "etiquetas": [t.strip() for t in
                          self.txt_etiquetas.text.get("1.0", tk.END).split(",")
                          if t.strip()],
            "archivo_original": (
                f"{os.path.splitext(self.original_filename)[0]}.mp4"
                if self.original_filename else ""
            ),
        }
        threading.Thread(target=self._hilo_publicacion, args=(news_data,),
                         daemon=True).start()

    def _hilo_publicacion(self, news_data):
        try:
            url = self.publisher_svr.publish(news_data)
            self.after(0, self._publicacion_ok, url)
        except Exception as e:
            self.after(0, self._publicacion_error, str(e))

    def _publicacion_ok(self, url):
        self._mover_a_papelera()
        self.lbl_pub_icon.config(text="✅", fg=ACCENT_GREEN)
        self.lbl_pub_title.config(text="¡Publicado con éxito!")
        self.lbl_pub_detail.config(text="Artículo creado en WordPress (pendiente de revisión)")
        self.lbl_pub_url.config(text=url or "")
        self.btn_new.pack(ipadx=20, ipady=4)
        self._set_status("¡Noticia publicada!", ACCENT_GREEN)
        self._toast("Publicación exitosa.", kind="success", duration=6000)
        self.step_indicator.complete_step(self.STEP_PUBLISH)
        self._processing = False
        self._auto_publish_pending = False

        # En modo watcher, auto-reset para procesar cola
        if self._watcher_active:
            self.after(4000, self._reset_flow)

    def _publicacion_error(self, msg):
        self._processing = False
        self._auto_publish_pending = False
        self.lbl_pub_icon.config(text="❌", fg=ACCENT_RED)
        self.lbl_pub_title.config(text="Error al publicar")
        self.lbl_pub_detail.config(text=msg)
        self.btn_new.pack(ipadx=20, ipady=4)
        self._set_status("Error al publicar.", ACCENT_RED)
        self._toast(msg, kind="error", duration=8000)

    # ── Papelera ─────────────────────────────────────────────────
    def _mover_a_papelera(self):
        if not self.archivo_audio or not os.path.exists(self.archivo_audio):
            return
        try:
            trash_dir = os.path.join(os.path.dirname(self.archivo_audio), "papelera")
            os.makedirs(trash_dir, exist_ok=True)
            destino = os.path.join(trash_dir, os.path.basename(self.archivo_audio))
            if os.path.exists(destino):
                base, ext = os.path.splitext(os.path.basename(self.archivo_audio))
                destino = os.path.join(
                    trash_dir, f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
                )
            shutil.move(self.archivo_audio, destino)
        except Exception:
            pass

    # ── Helpers UI ───────────────────────────────────────────────
    def _field_label(self, parent, text):
        tk.Label(parent, text=text, bg=BG_DARK, fg=FG_SECONDARY,
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor=tk.W, pady=(0, 5))

    def _limpiar_todo(self):
        self.txt_titulo.text.delete("1.0", tk.END)
        self.txt_entradilla.text.delete("1.0", tk.END)
        self._set_html_contenido("")
        self.txt_etiquetas.text.delete("1.0", tk.END)
        self._set_status("Borrador limpiado.", ACCENT_GREEN)
        self._toast("Campos limpiados.", kind="info")

    def _open_settings(self):
        SettingsDialog(self, on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        if self._watcher_active:
            self._stop_watcher()
            self._start_watcher()

    def destroy(self):
        self._stop_progress_anim()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
        super().destroy()


if __name__ == "__main__":
    app = PublicadorApp()
    app.withdraw() # Lo ocultamos inicialmente
    
    splash = SplashScreen(app)
    
    def on_loaded():
        try:
            splash.destroy()
        except:
            pass
        # Inicializar los servicios de IA ahora que están importados
        app._init_services()
        app.deiconify() # Mostrar la ventana principal

    def load_and_start():
        load_resources(splash)
        app.after(0, on_loaded)

    loader_thread = threading.Thread(target=load_and_start, daemon=True)
    loader_thread.start()
    
    app.mainloop()
