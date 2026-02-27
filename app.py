"""
HTV · Publicador Inteligente
UI wizard paso-a-paso con file watcher automático.
"""

import os
import queue
import shutil
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, ttk

import ui.splash as splash_loader
from ui.dialogs import SettingsDialog, VerificationDialog
from ui.settings import load_settings as _load_settings
from ui.theme import (
    ACCENT_BLUE,
    ACCENT_CYAN,
    ACCENT_GOLD,
    ACCENT_GREEN,
    ACCENT_ORANGE,
    ACCENT_PURPLE,
    ACCENT_RED,
    ACCENT_YELLOW,
    BG_CARD,
    BG_CARD_SOFT,
    BG_DARK,
    BG_HEADER,
    BG_INPUT,
    BORDER,
    BORDER_BRIGHT,
    FG_MUTED,
    FG_PRIMARY,
    FG_SECONDARY,
    FONT_FAMILY,
    SHADOW_DARK,
)
from ui.widgets import (
    HTMLRenderer,
    RoundedText,
    StepIndicator,
    ToggleSwitch,
    rounded_rect as _rounded_rect,
)


class PublicadorApp(tk.Tk):
    STEP_AUDIO   = 0
    STEP_PROCESS = 1
    STEP_EDIT    = 2
    STEP_PUBLISH = 3

    def __init__(self):
        super().__init__()
        self.title("HTV · Publicador Inteligente")
        self._configure_window_geometry()
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
        self._edit_scroll_bound = False

        self._build_ui()
        self._show_step(self.STEP_AUDIO)

    def _configure_window_geometry(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        max_w = max(720, sw - 80)
        max_h = max(520, sh - 100)
        width = min(max_w, min(1280, max(820, int(sw * 0.78))))
        height = min(max_h, min(900, max(560, int(sh * 0.80))))
        self.geometry(f"{width}x{height}")
        self.minsize(min(820, max_w), min(560, max_h))

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
            if not all(
                [
                    splash_loader.TranscriptionService,
                    splash_loader.WriterService,
                    splash_loader.PublisherService,
                    splash_loader.VerificationService,
                ]
            ):
                raise RuntimeError("Servicios no cargados. Reinicia la aplicación.")

            self.transcription_svr = splash_loader.TranscriptionService()
            self.writer_svr = splash_loader.WriterService()
            self.publisher_svr = splash_loader.PublisherService()
            self.verification_svr = splash_loader.VerificationService()
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

        self.update_idletasks()
        wrap = max(220, min(520, self.winfo_width() - 160))

        toast = tk.Frame(self, bg=bc)
        toast.place(relx=1.0, rely=1.0, x=-16, y=-16, anchor="se")
        inner = tk.Frame(toast, bg=bgc)
        inner.pack(padx=2, pady=2, fill=tk.BOTH, expand=True)
        icons = {"info": "ℹ", "success": "✓", "error": "✕", "warning": "⚠"}
        tk.Label(inner, text=icons.get(kind, "ℹ"), bg=bgc, fg=bc,
                 font=(FONT_FAMILY, 14, "bold")).pack(side=tk.LEFT, padx=(14, 8), pady=12)
        tk.Label(inner, text=message, bg=bgc, fg=FG_PRIMARY,
                 font=(FONT_FAMILY, 10), wraplength=wrap, justify=tk.LEFT
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

    def _create_center_stage(self, parent):
        host = tk.Frame(parent, bg=BG_DARK)
        host.pack(fill=tk.BOTH, expand=True)
        host.grid_rowconfigure(0, weight=1)
        host.grid_rowconfigure(2, weight=1)
        host.grid_columnconfigure(0, weight=1)
        center = tk.Frame(host, bg=BG_DARK)
        center.grid(row=1, column=0)
        return center

    # ── Step builders ────────────────────────────────────────────
    def _build_step_audio(self, parent):
        """Paso 1 — Selección de audio / Esperando watcher."""
        center = self._create_center_stage(parent)

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
        center = self._create_center_stage(parent)

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
        self._edit_canvas.bind("<Enter>", lambda e: self._bind_edit_scroll())
        self._edit_canvas.bind("<Leave>", lambda e: self._unbind_edit_scroll())

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
        center = self._create_center_stage(parent)

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

        if idx == self.STEP_EDIT:
            self._bind_edit_scroll()
        else:
            self._unbind_edit_scroll()

    def _bind_edit_scroll(self):
        if self._edit_scroll_bound or not hasattr(self, "_edit_canvas"):
            return
        self._edit_canvas.bind("<MouseWheel>", self._on_edit_scroll)
        self._edit_canvas.bind("<Button-4>", self._on_edit_scroll_linux_up)
        self._edit_canvas.bind("<Button-5>", self._on_edit_scroll_linux_down)
        self._edit_scroll_bound = True

    def _unbind_edit_scroll(self):
        if not self._edit_scroll_bound or not hasattr(self, "_edit_canvas"):
            return
        self._edit_canvas.unbind("<MouseWheel>")
        self._edit_canvas.unbind("<Button-4>")
        self._edit_canvas.unbind("<Button-5>")
        self._edit_scroll_bound = False

    def _on_edit_scroll(self, event):
        self._edit_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_edit_scroll_linux_up(self, event):
        self._edit_canvas.yview_scroll(-1, "units")

    def _on_edit_scroll_linux_down(self, event):
        self._edit_canvas.yview_scroll(1, "units")

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
        if not splash_loader.HAS_WATCHDOG:
            self._toast("Instala 'watchdog': pip install watchdog", kind="error")
            self.toggle_watcher.set(False)
            return
        settings = _load_settings()
        folder = settings.get("watch_folder", "")
        if not folder or not os.path.isdir(folder):
            self._toast("Configura la carpeta de vigilancia en ⚙.", kind="warning")
            self.toggle_watcher.set(False)
            return

        handler = splash_loader.Mp3Handler(lambda path: self.after(0, self._on_mp3_detected, path))
        self._observer = splash_loader.Observer()
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
        self._unbind_edit_scroll()
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
    
    splash = splash_loader.SplashScreen(app)
    
    def on_loaded():
        try:
            splash.destroy()
        except:
            pass
        # Inicializar los servicios de IA ahora que están importados
        app._init_services()
        app.deiconify() # Mostrar la ventana principal

    def load_and_start():
        splash_loader.load_resources(splash)
        app.after(0, on_loaded)

    loader_thread = threading.Thread(target=load_and_start, daemon=True)
    loader_thread.start()
    
    app.mainloop()
