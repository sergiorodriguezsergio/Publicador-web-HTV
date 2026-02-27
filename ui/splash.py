import os
import threading
import time
import tkinter as tk

from ui.theme import ACCENT_CYAN, BG_CARD, BG_DARK, FG_SECONDARY, FONT_FAMILY

TranscriptionService = None
WriterService = None
PublisherService = None
VerificationService = None
HAS_WATCHDOG = False
Observer = None
FileSystemEventHandler = object
Mp3Handler = None


class SplashScreen(tk.Toplevel):
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

        tk.Label(main_f, text="📺", font=("Segoe UI Emoji", 50), bg=BG_DARK, fg=ACCENT_CYAN).pack(
            pady=(40, 10)
        )
        tk.Label(
            main_f,
            text="HTV · PUBLICADOR WEB",
            font=(FONT_FAMILY, 16, "bold"),
            bg=BG_DARK,
            fg="white",
        ).pack()
        tk.Label(
            main_f,
            text="SISTEMA INTELIGENTE DE REDACCIÓN",
            font=(FONT_FAMILY, 8),
            bg=BG_DARK,
            fg=ACCENT_CYAN,
        ).pack(pady=(2, 20))

        self.lbl_status = tk.Label(
            main_f,
            text="Iniciando componentes...",
            font=(FONT_FAMILY, 9),
            bg=BG_DARK,
            fg=FG_SECONDARY,
        )
        self.lbl_status.pack()

        self.canvas = tk.Canvas(main_f, width=300, height=2, bg=BG_CARD, highlightthickness=0)
        self.canvas.pack(pady=15)
        self.progress = self.canvas.create_rectangle(0, 0, 0, 2, fill=ACCENT_CYAN, outline="")

        self._progress_val = 0
        self._anim_id = None
        self._animate()

    def _animate(self):
        try:
            if not self.winfo_exists():
                return
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
            except Exception:
                pass
        super().destroy()

    def update_status(self, text):
        self.lbl_status.config(text=text)
        self.update()


def load_resources(splash):
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
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            HAS_WATCHDOG = True

            class _Mp3Handler(FileSystemEventHandler):
                _EXTS = {
                    ".mp4",
                    ".mp3",
                    ".wav",
                    ".m4a",
                    ".ogg",
                    ".flac",
                    ".webm",
                    ".mpeg",
                    ".mpg",
                    ".mov",
                }

                def __init__(self, callback):
                    super().__init__()
                    self._callback = callback
                    self._processed = set()

                def on_created(self, event):
                    if event.is_directory:
                        return
                    raw = event.src_path
                    src = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    if os.path.splitext(src)[1].lower() in self._EXTS:
                        if src in self._processed:
                            return
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
                        except OSError:
                            pass
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

