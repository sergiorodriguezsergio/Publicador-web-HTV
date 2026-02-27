import json
import os
import shutil
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from ui.settings import CONFIG_DIR, PROMPTS_PATH, center_on_parent, load_settings, save_settings
from ui.theme import (
    ACCENT_BLUE,
    ACCENT_CYAN,
    ACCENT_GOLD,
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_YELLOW,
    BG_CARD,
    BG_DARK,
    BG_HEADER,
    BG_INPUT,
    BORDER_BRIGHT,
    FG_MUTED,
    FG_PRIMARY,
    FG_SECONDARY,
    FONT_FAMILY,
)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.title("Configuración")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.grab_set()
        center_on_parent(self, parent, 900, 700)
        self._on_save = on_save

        self.settings = load_settings()
        try:
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                self.prompts = json.load(f)
        except Exception:
            self.prompts = {}

        hdr = tk.Frame(self, bg=BG_HEADER, height=50)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="⚙  CONFIGURACIÓN",
            bg=BG_HEADER,
            fg="white",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor=tk.W, padx=16, pady=10)

        style = ttk.Style(self)
        style.configure("Dark.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure(
            "Dark.TNotebook.Tab",
            background=BG_CARD,
            foreground=FG_PRIMARY,
            font=(FONT_FAMILY, 10, "bold"),
            padding=[14, 8],
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", ACCENT_BLUE)],
            foreground=[("selected", "white")],
        )

        nb = ttk.Notebook(self, style="Dark.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tab_gen = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_gen, text="📂  General")

        tk.Label(
            tab_gen,
            text="Carpeta de vigilancia (watcher):",
            bg=BG_DARK,
            fg=FG_SECONDARY,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(anchor=tk.W, padx=12, pady=(16, 4))
        folder_row = tk.Frame(tab_gen, bg=BG_DARK)
        folder_row.pack(fill=tk.X, padx=12)
        self.entry_folder = tk.Entry(
            folder_row,
            bg=BG_INPUT,
            fg=FG_PRIMARY,
            font=(FONT_FAMILY, 10),
            insertbackground=ACCENT_BLUE,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=BORDER_BRIGHT,
            highlightcolor=ACCENT_CYAN,
        )
        self.entry_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_folder.insert(0, self.settings.get("watch_folder", ""))
        tk.Button(
            folder_row,
            text="📁",
            bg=BG_CARD,
            fg=FG_PRIMARY,
            font=(FONT_FAMILY, 12),
            relief=tk.FLAT,
            cursor="hand2",
            command=self._browse_folder,
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(
            tab_gen,
            text="Los archivos MP3 que aparezcan en esta carpeta serán\n"
            "procesados automáticamente cuando el watcher esté activo.",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=(FONT_FAMILY, 8),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(4, 0))

        tk.Frame(tab_gen, bg=BG_DARK, height=24).pack()

        trash_card = tk.Frame(tab_gen, bg=BG_CARD)
        trash_card.pack(fill=tk.X, padx=12, pady=8)
        tk.Label(
            trash_card,
            text="🗑  Papelera",
            bg=BG_CARD,
            fg=FG_PRIMARY,
            font=(FONT_FAMILY, 10, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(
            trash_card,
            text="Elimina permanentemente los archivos de audio ya procesados.",
            bg=BG_CARD,
            fg=FG_SECONDARY,
            font=(FONT_FAMILY, 8),
        ).pack(anchor=tk.W, padx=14, pady=(0, 8))
        tk.Button(
            trash_card,
            text="🗑  Vaciar papelera",
            bg=ACCENT_RED,
            fg="white",
            font=(FONT_FAMILY, 10, "bold"),
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._vaciar_papelera,
        ).pack(anchor=tk.W, padx=14, pady=(0, 14))

        self.editors = {}
        tab_labels = {"redaccion": "✍️  Redacción", "verificacion": "🔍 Verificación"}
        for key in ["redaccion", "verificacion"]:
            tab = tk.Frame(nb, bg=BG_DARK)
            nb.add(tab, text=tab_labels[key])
            cfg = self.prompts.get(key, {})

            tk.Label(
                tab,
                text="Modelo:",
                bg=BG_DARK,
                fg=FG_SECONDARY,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W, padx=12, pady=(12, 2))
            entry_model = tk.Entry(
                tab,
                bg=BG_INPUT,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 10),
                insertbackground=ACCENT_BLUE,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground=BORDER_BRIGHT,
                highlightcolor=ACCENT_CYAN,
            )
            entry_model.pack(fill=tk.X, padx=12, pady=(0, 8))
            entry_model.insert(0, cfg.get("modelo", ""))

            tk.Label(
                tab,
                text="System Prompt:",
                bg=BG_DARK,
                fg=FG_SECONDARY,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W, padx=12, pady=(4, 2))
            txt_sys = ScrolledText(
                tab,
                bg=BG_INPUT,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 9),
                insertbackground=ACCENT_BLUE,
                relief=tk.FLAT,
                height=14,
                highlightthickness=1,
                highlightbackground=BORDER_BRIGHT,
                highlightcolor=ACCENT_CYAN,
                wrap=tk.WORD,
            )
            txt_sys.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
            txt_sys.insert("1.0", cfg.get("system_prompt", ""))

            tk.Label(
                tab,
                text="User Prompt Template:",
                bg=BG_DARK,
                fg=FG_SECONDARY,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W, padx=12, pady=(4, 2))
            txt_usr = ScrolledText(
                tab,
                bg=BG_INPUT,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 9),
                insertbackground=ACCENT_BLUE,
                relief=tk.FLAT,
                height=5,
                highlightthickness=1,
                highlightbackground=BORDER_BRIGHT,
                highlightcolor=ACCENT_CYAN,
                wrap=tk.WORD,
            )
            txt_usr.pack(fill=tk.X, padx=12, pady=(0, 8))
            txt_usr.insert("1.0", cfg.get("user_prompt_template", ""))

            self.editors[key] = (entry_model, txt_sys, txt_usr)

        btn_bar = tk.Frame(self, bg=BG_CARD, height=55)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_bar.pack_propagate(False)
        tk.Button(
            btn_bar,
            text="💾  Guardar",
            bg=ACCENT_GREEN,
            fg="white",
            font=(FONT_FAMILY, 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=6,
            cursor="hand2",
            command=self._save,
        ).pack(side=tk.LEFT, padx=12, pady=10)
        tk.Button(
            btn_bar,
            text="Cancelar",
            bg=FG_MUTED,
            fg="white",
            font=(FONT_FAMILY, 10),
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self.destroy,
        ).pack(side=tk.LEFT)

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
        if messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar permanentemente {len(files)} archivo(s)?",
            parent=self,
        ):
            try:
                shutil.rmtree(trash)
                os.makedirs(trash, exist_ok=True)
                messagebox.showinfo("Hecho", "Papelera vaciada.", parent=self)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=self)

    def _save(self):
        self.settings["watch_folder"] = self.entry_folder.get().strip()
        save_settings(self.settings)

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


class VerificationDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        correcciones,
        texto_corregido,
        fuentes,
        aviso,
        callback_aplicar,
        texto_original=None,
    ):
        super().__init__(parent)
        self.title("Verificación periodística")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.grab_set()
        center_on_parent(self, parent, 860, 720)

        self.texto_corregido = texto_corregido
        self.texto_original = texto_original or {}
        self.callback_aplicar = callback_aplicar
        self.checks = []

        hdr = tk.Frame(self, bg=BG_HEADER, height=55)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="🔍  VERIFICACIÓN CON IA + BÚSQUEDA WEB",
            bg=BG_HEADER,
            fg="white",
            font=(FONT_FAMILY, 13, "bold"),
        ).pack(anchor=tk.W, padx=16, pady=12)

        main = tk.Frame(self, bg=BG_DARK)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        if aviso:
            af = tk.Frame(main, bg=BG_CARD)
            af.pack(fill=tk.X, pady=(0, 10))
            tk.Label(
                af,
                text=aviso,
                bg=BG_CARD,
                fg=ACCENT_YELLOW,
                font=(FONT_FAMILY, 9, "italic"),
                wraplength=790,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, padx=14, pady=10)

        canvas_f = tk.Frame(main, bg=BG_DARK)
        canvas_f.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        canvas = tk.Canvas(canvas_f, bg=BG_DARK, highlightthickness=0)
        sb = tk.Scrollbar(canvas_f, orient="vertical", command=canvas.yview)
        self.items_frame = tk.Frame(canvas, bg=BG_DARK)
        self.items_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
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
            tk.Checkbutton(
                row,
                variable=var,
                bg=BG_CARD,
                activebackground=BG_CARD,
                selectcolor=ACCENT_BLUE,
            ).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(
                row,
                text=f"Corrección #{num}",
                bg=BG_CARD,
                fg=ACCENT_BLUE,
                font=(FONT_FAMILY, 10, "bold"),
            ).pack(side=tk.LEFT)
            body = tk.Frame(card, bg=BG_CARD)
            body.pack(fill=tk.X, padx=36, pady=(0, 10))
            tk.Label(
                body,
                text="❌ Original:",
                bg=BG_CARD,
                fg=ACCENT_RED,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W)
            tk.Label(
                body,
                text=corr.get("original", ""),
                bg=BG_CARD,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 9),
                wraplength=720,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)
            tk.Label(
                body,
                text="✅ Corrección:",
                bg=BG_CARD,
                fg=ACCENT_GREEN,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W, pady=(6, 0))
            tk.Label(
                body,
                text=corr.get("corregido", ""),
                bg=BG_CARD,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 9),
                wraplength=720,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)
            expl = corr.get("explicacion", "")
            if expl:
                tk.Label(
                    body,
                    text=f"💡 {expl}",
                    bg=BG_CARD,
                    fg=FG_SECONDARY,
                    font=(FONT_FAMILY, 8, "italic"),
                    wraplength=720,
                ).pack(anchor=tk.W, pady=(4, 0))
            fecha_ref = corr.get("fecha_referencia", "")
            if fecha_ref:
                tk.Label(
                    body,
                    text=f"📅 Fecha de la fuente: {fecha_ref}",
                    bg=BG_CARD,
                    fg=ACCENT_GOLD,
                    font=(FONT_FAMILY, 8),
                ).pack(anchor=tk.W, pady=(2, 0))
            src = corr.get("fuente", "")
            if src:
                lbl = tk.Label(
                    body,
                    text=f"🔗 {src}",
                    bg=BG_CARD,
                    fg=ACCENT_CYAN,
                    font=(FONT_FAMILY, 8, "underline"),
                    cursor="hand2",
                    wraplength=720,
                )
                lbl.pack(anchor=tk.W, pady=(2, 0))
                lbl.bind("<Button-1>", lambda e, u=src: webbrowser.open(u))

        if fuentes:
            sf = tk.Frame(main, bg=BG_CARD)
            sf.pack(fill=tk.X, pady=(8, 0))
            tk.Label(
                sf,
                text="📚 Fuentes consultadas:",
                bg=BG_CARD,
                fg=FG_SECONDARY,
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(anchor=tk.W, padx=14, pady=(10, 4))
            for url in fuentes:
                link = tk.Label(
                    sf,
                    text=f"  🔗 {url}",
                    bg=BG_CARD,
                    fg=ACCENT_CYAN,
                    font=(FONT_FAMILY, 8, "underline"),
                    cursor="hand2",
                )
                link.pack(anchor=tk.W, padx=14, pady=1)
                link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        btns = tk.Frame(self, bg=BG_CARD, height=55)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        btns.pack_propagate(False)
        tk.Button(
            btns,
            text="✓  Aplicar correcciones",
            bg=ACCENT_GREEN,
            fg="white",
            font=(FONT_FAMILY, 11, "bold"),
            relief=tk.FLAT,
            padx=18,
            pady=7,
            cursor="hand2",
            command=self._aplicar,
        ).pack(side=tk.LEFT, padx=12, pady=10)
        tk.Button(
            btns,
            text="✕  Cancelar",
            bg=FG_MUTED,
            fg="white",
            font=(FONT_FAMILY, 10),
            relief=tk.FLAT,
            padx=14,
            pady=7,
            cursor="hand2",
            command=self.destroy,
        ).pack(side=tk.LEFT)

    def _aplicar(self):
        omitidos = [str(c["numero"]) for v, c in self.checks if not v.get()]
        aplicados = [(v, c) for v, c in self.checks if v.get()]
        if omitidos:
            dlg = tk.Toplevel(self)
            dlg.title("Confirmar")
            dlg.configure(bg=BG_DARK)
            dlg.grab_set()
            dlg.resizable(False, False)
            center_on_parent(dlg, self, 440, 180)
            tk.Label(
                dlg,
                text=f"Se omitirán las correcciones: #{', #'.join(omitidos)}.\n"
                "Esas partes quedarán como estaban en el borrador.",
                bg=BG_DARK,
                fg=FG_PRIMARY,
                font=(FONT_FAMILY, 10),
                wraplength=400,
                justify=tk.CENTER,
            ).pack(pady=24)
            row = tk.Frame(dlg, bg=BG_DARK)
            row.pack()
            result = [False]

            def ok():
                result[0] = True
                dlg.destroy()

            def cancel():
                dlg.destroy()

            tk.Button(
                row,
                text="Continuar",
                bg=ACCENT_GREEN,
                fg="white",
                font=(FONT_FAMILY, 10, "bold"),
                relief=tk.FLAT,
                padx=16,
                pady=6,
                cursor="hand2",
                command=ok,
            ).pack(side=tk.LEFT, padx=8)
            tk.Button(
                row,
                text="Volver",
                bg=FG_MUTED,
                fg="white",
                font=(FONT_FAMILY, 10),
                relief=tk.FLAT,
                padx=16,
                pady=6,
                cursor="hand2",
                command=cancel,
            ).pack(side=tk.LEFT)
            dlg.wait_window()
            if not result[0]:
                return

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
