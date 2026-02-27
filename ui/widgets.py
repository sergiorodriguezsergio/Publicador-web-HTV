import tkinter as tk
import tkinter.font as tkfont
from html.parser import HTMLParser

from ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    BG_DARK,
    BG_INPUT,
    BORDER_BRIGHT,
    FG_MUTED,
    FG_PRIMARY,
    FG_SECONDARY,
    FONT_FAMILY,
)


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedText(tk.Canvas):
    def __init__(
        self,
        parent,
        text_height=2,
        radius=10,
        border_color=BORDER_BRIGHT,
        focus_color=ACCENT_CYAN,
        bg_fill=BG_INPUT,
        **text_kw,
    ):
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
            self,
            height=text_height,
            bg=bg_fill,
            relief=tk.FLAT,
            highlightthickness=0,
            borderwidth=0,
            padx=10,
            pady=6,
            **text_kw,
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
        rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            self._r,
            outline=color,
            fill=self._fill,
            width=1.5,
            tags="border",
        )
        self.tag_lower("border")
        pad = 6
        self.coords(self._win, pad + 2, pad)
        self.itemconfig(self._win, width=max(1, w - 2 * pad - 4), height=max(1, h - 2 * pad))


class ToggleSwitch(tk.Canvas):
    def __init__(
        self,
        parent,
        command=None,
        initial=False,
        width=48,
        height=24,
        bg_on=ACCENT_GREEN,
        bg_off=FG_MUTED,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent.cget("bg"),
            highlightthickness=0,
            cursor="hand2",
        )
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
        rounded_rect(self, 1, 1, w - 1, h - 1, r, fill=bg, outline=bg)
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


class StepIndicator(tk.Canvas):
    STEPS = [("🎙", "Audio"), ("🤖", "Procesar"), ("📝", "Editar"), ("🚀", "Publicar")]
    _FA_STEP_ICONS = ("\uf130", "\uf544", "\uf044", "\uf135")
    _FA_DONE_ICON = "\uf00c"

    def __init__(self, parent):
        super().__init__(parent, bg=BG_DARK, highlightthickness=0, height=70)
        self._current = 0
        self._completed = set()
        self._fa_font_family = self._detect_fa_font()
        self.bind("<Configure>", self._draw)

    def _detect_fa_font(self):
        try:
            families = list(tkfont.families())
        except tk.TclError:
            return None

        priority = [
            "Font Awesome 6 Free Solid",
            "Font Awesome 5 Free Solid",
            "Font Awesome 6 Free",
            "Font Awesome 5 Free",
        ]
        by_lower = {f.lower(): f for f in families}
        for pref in priority:
            match = by_lower.get(pref.lower())
            if match:
                return match

        fallback = [f for f in families if "font awesome" in f.lower()]
        if fallback:
            return sorted(fallback, key=lambda n: ("solid" not in n.lower(), n))[0]
        return None

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
        if w < 60 or h < 40:
            return
        n = len(self.STEPS)
        sw = w / n
        r = max(12, min(18, int(h * 0.26)))
        yc = max(r + 2, int(h * 0.38))
        line_pad = r + max(4, int(r * 0.35))
        circle_font = max(8, min(11, int(r * 0.55)))
        label_font = max(8, min(10, int(r * 0.52)))
        label_y = min(h - 8, yc + r + max(10, int(h * 0.16)))

        for i in range(1, n):
            x1 = sw * (i - 1) + sw / 2 + line_pad
            x2 = sw * i + sw / 2 - line_pad
            color = ACCENT_CYAN if i <= self._current else BORDER_BRIGHT
            self.create_line(x1, yc, x2, yc, fill=color, width=2)

        for i, (icon, label) in enumerate(self.STEPS):
            cx = sw * i + sw / 2
            if i in self._completed:
                fill, tcol = ACCENT_GREEN, "white"
                if self._fa_font_family:
                    txt = self._FA_DONE_ICON
                    txt_font = (self._fa_font_family, circle_font, "normal")
                else:
                    txt = "✓"
                    txt_font = (FONT_FAMILY, circle_font, "bold")
            elif i == self._current:
                fill, tcol = ACCENT_CYAN, "white"
                if self._fa_font_family:
                    txt = self._FA_STEP_ICONS[i]
                    txt_font = (self._fa_font_family, circle_font, "normal")
                else:
                    txt = icon
                    txt_font = (FONT_FAMILY, circle_font, "bold")
            else:
                fill, txt, tcol = BORDER_BRIGHT, str(i + 1), FG_MUTED
                txt_font = (FONT_FAMILY, circle_font, "bold")

            self.create_oval(cx - r, yc - r, cx + r, yc + r, fill=fill, outline=fill)
            self.create_text(cx, yc, text=txt, fill=tcol, font=txt_font)
            lcol = FG_PRIMARY if i == self._current else FG_SECONDARY
            weight = "bold" if i == self._current else ""
            self.create_text(cx, label_y, text=label, fill=lcol, font=(FONT_FAMILY, label_font, weight))


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
