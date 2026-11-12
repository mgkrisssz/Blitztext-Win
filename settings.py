"""
Einstellungsfenster fuer Blitztext (Doppelklick auf das Tray-Icon).

Design: randlose helle "Bubble" mit runden Ecken (DWM), flache Flaechen,
drei umschaltbare Stile (cfg["theme"]):
  "mix"    - weiss, Lora-Titel + Familjen Grotesk, Terrakotta/Gruen (Standard)
  "claude" - warmes Creme, gleiche Schriften, Terrakotta
  "hell"   - Segoe UI Variable, Windows-Blau
Die Schriften liegen als TTF in ./fonts und werden nur fuer diesen Prozess
geladen (AddFontResourceEx FR_PRIVATE), nichts wird installiert.

Extras: grosses Schliessen-✕ mit Hover-Kreis, Live-Mikrofonpegel (im Mix als
Ampel gruen/bernstein/rot), gleitende Schalter, pulsierende Hotkey-Aufnahme,
sanftes Einblenden beim Oeffnen.

Laeuft in einem eigenen Thread mit eigener Tk-Instanz (Muster wie overlay.py);
Aenderungen schreiben direkt in cfg und speichern sofort.
"""

import os
import re
import ctypes
import threading

import numpy as np
import sounddevice as sd
from PIL import Image, ImageDraw, ImageTk

from i18n import t, set_language

_lock = threading.Lock()
_open = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(APP_DIR, "fonts")

LANGS = [("Automatisch", ""), ("Deutsch", "de"), ("Englisch", "en"),
         ("Ungarisch", "hu"), ("Französisch", "fr"), ("Spanisch", "es"),
         ("Italienisch", "it"), ("Portugiesisch", "pt"), ("Niederländisch", "nl"),
         ("Polnisch", "pl"), ("Tschechisch", "cs"), ("Türkisch", "tr"),
         ("Russisch", "ru"), ("Ukrainisch", "uk"), ("Arabisch", "ar"),
         ("Japanisch", "ja"), ("Chinesisch", "zh")]

# Whisper-Modelle: (Anzeigename, interner Name). Kleiner = schneller + weniger Speicher,
# groesser = genauer. Beim ersten Auswaehlen wird das Modell einmalig heruntergeladen.
MODELS = [("Tiny – winzig, ungenau", "tiny"),
          ("Base – sehr schnell", "base"),
          ("Small – schnell, gut (CPU)", "small"),
          ("Medium – genauer, mehr Power", "medium"),
          ("Turbo – fast wie Large, schneller", "large-v3-turbo"),
          ("Large-v3 – beste Qualität (GPU)", "large-v3")]

# Ampel-Farben fuer den Mikrofonpegel (Stil "mix")
AMPEL = [(0.88, "#c53929"), (0.70, "#d9930d"), (0.0, "#2d8659")]

THEMES = {
    "mix": dict(
        label="Mix",
        bg="#ffffff", border="#e5e4de", text="#2b2a25", subtle="#8d8b80",
        divider="#f1f0ea", sect="#c96442",
        chip_bg="#fcfcfa", chip_border="#dcdad0", chip_text="#4a483d",
        chip_hot="#c96442", chip_hot2="#dd8a68",
        tog_off="#d08a70", tog_on="#2d8659",
        field_bg="#ffffff", field_border="#dcdad0",
        btn_bg="#c96442", btn_border="#c96442", btn_text="#ffffff",
        seg_bg="#edece6",
        meter_bg="#edece6", meter="ampel",
        close_hover="#f2f1ec",
        serif=True,
    ),
    "claude": dict(
        label="Claude",
        bg="#faf9f5", border="#e8e5da", text="#35322a", subtle="#94907f",
        divider="#efede3", sect="#94907f",
        chip_bg="#ffffff", chip_border="#ddd9c9", chip_text="#56523f",
        chip_hot="#c96442", chip_hot2="#dd8a68",
        tog_off="#d9d5c5", tog_on="#c96442",
        field_bg="#ffffff", field_border="#ddd9c9",
        btn_bg="#ffffff", btn_border="#ddd9c9", btn_text="#56523f",
        seg_bg="#ebe8dc",
        meter_bg="#ebe8dc", meter="#c96442",
        close_hover="#efede4",
        serif=True,
    ),
    "hell": dict(
        label="Hell",
        bg="#ffffff", border="#e4e6ea", text="#1b1e24", subtle="#878d97",
        divider="#f0f1f4", sect="#878d97",
        chip_bg="#fafbfc", chip_border="#d9dce1", chip_text="#3c414a",
        chip_hot="#0f6cbd", chip_hot2="#5b97d6",
        tog_off="#d4d7dc", tog_on="#0f6cbd",
        field_bg="#ffffff", field_border="#d9dce1",
        btn_bg="#ffffff", btn_border="#d9dce1", btn_text="#3c414a",
        seg_bg="#eceef1",
        meter_bg="#eceef1", meter="#0f6cbd",
        close_hover="#f0f1f4",
        serif=False,
    ),
}

_fonts_loaded = False

def _load_fonts():
    """Mitgelieferte TTFs nur fuer diesen Prozess registrieren (FR_PRIVATE)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    try:
        for name in os.listdir(FONTS_DIR):
            if name.lower().endswith(".ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(
                    os.path.join(FONTS_DIR, name), 0x10, 0)  # 0x10 = FR_PRIVATE
    except Exception as e:
        print(f"[Einstellungen] Schriften laden: {e}")


def _hwnd_of(root):
    h = ctypes.windll.user32.GetParent(root.winfo_id())
    return h or root.winfo_id()


def _round_corners(root):
    """Runde Fensterecken (Win11); ohne Effekt auf aelteren Systemen."""
    try:
        root.update_idletasks()
        v = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            _hwnd_of(root), 33, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def open_settings(ctx):
    """Fenster oeffnen (nur eines gleichzeitig). ctx: cfg, save, devices,
    autostart_get, autostart_set, open_vocab, set_hotkey, reload_model, suspend,
    resolve_device."""
    global _open
    with _lock:
        if _open:
            return
        _open = True

    def _runner():
        global _open
        try:
            _run(ctx)
        except Exception as e:
            print(f"[Einstellungen] Fenster-Fehler: {e}")
        finally:
            _open = False

    threading.Thread(target=_runner, daemon=True).start()


# Tk-Keysym -> pynput-Hotkey-String (fuer die Hotkey-Aufnahme im Fenster)
_KS_MAP = {"space": "<space>", "Pause": "<pause>", "Insert": "<insert>",
           "Home": "<home>", "End": "<end>", "Prior": "<page_up>",
           "Next": "<page_down>", "Tab": "<tab>", "Scroll_Lock": "<scroll_lock>"}
_MOD_SYMS = ("Control", "Alt", "Shift", "Win", "Super", "Meta", "ISO_Level3")

def _keysym_to_hotkey(e):
    """None = weiter warten (nur Modifier), '__clear__', '__invalid__' oder Hotkey-String."""
    ks = e.keysym
    if any(ks.startswith(m) for m in _MOD_SYMS):
        return None
    if ks in ("Delete", "BackSpace"):
        return "__clear__"
    if re.fullmatch(r"F\d{1,2}", ks):
        key = "<%s>" % ks.lower()
    elif len(ks) == 1:
        key = ks.lower()
    elif ks in _KS_MAP:
        key = _KS_MAP[ks]
    else:
        return "__invalid__"
    mods = []
    if e.state & 4:
        mods.append("<ctrl>")
    if e.state & 131072:          # Alt (Windows)
        mods.append("<alt>")
    if (e.state & 1) and key.startswith("<"):
        mods.append("<shift>")
    return "+".join(mods + [key])


_SS = 4  # Supersampling: mit PIL 4x so gross zeichnen, dann glatt herunterskalieren

def _pill(c, w, h, radius, fill, outline=None, knob=None):
    """Antialiased abgerundetes Rechteck (+ optional 1px-Rand und runder Knopf)
    als Tk-Bild. Referenz am Canvas halten (c._imgs), sonst raeumt es der GC weg."""
    img = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * _SS - 1, h * _SS - 1),
                        radius=int(radius * _SS), fill=fill,
                        outline=outline, width=_SS if outline else 0)
    if knob:
        x, r, col = knob
        cy = h * _SS / 2
        d.ellipse((x * _SS - r * _SS, cy - r * _SS,
                   x * _SS + r * _SS, cy + r * _SS), fill=col)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS), master=c)


def _circle(c, d_px, color):
    """Antialiased Kreis (Hover-Flaeche des Schliessen-Knopfs)."""
    img = Image.new("RGBA", (d_px * _SS, d_px * _SS), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, d_px * _SS - 1, d_px * _SS - 1), fill=color)
    return ImageTk.PhotoImage(img.resize((d_px, d_px), Image.LANCZOS), master=c)


def _run(ctx):
    import tkinter as tk
    import tkinter.font as tkfont

    cfg = ctx["cfg"]
    save = ctx["save"]

    _load_fonts()

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)          # keine Titelleiste -> Bubble
    root.attributes("-topmost", True)

    fams = set(tkfont.families())

    WW = 350
    holder = {"content": None, "meter_draw": None}
    cap = {"which": None, "redraw": None, "clear_ok": False, "pulse": None}

    # ---- Live-Mikrofonpegel ------------------------------------------------
    meter = {"level": 0.0, "stream": None}

    def meter_stop():
        s = meter["stream"]
        meter["stream"] = None
        meter["level"] = 0.0
        if s is not None:
            try:
                s.stop(); s.close()
            except Exception:
                pass

    def meter_start():
        meter_stop()
        try:
            dev = None
            if ctx.get("resolve_device"):
                dev = ctx["resolve_device"](cfg.get("input_device"))
            def cb(indata, frames, t, status):
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                meter["level"] = min(1.0, rms * 18.0)
            meter["stream"] = sd.InputStream(device=dev, samplerate=16000,
                                             channels=1, dtype="float32",
                                             callback=cb)
            meter["stream"].start()
        except Exception as e:
            print(f"[Einstellungen] Pegelanzeige: {e}")

    def meter_tick():
        if not root.winfo_exists():
            return
        draw = holder["meter_draw"]
        if draw:
            draw(meter["level"])
        root.after(80, meter_tick)

    # ---- Hotkey-Aufnahme -----------------------------------------------------
    def end_capture(msg=None):
        d = cap["redraw"]
        cap["which"] = None
        if cap["pulse"]:
            try:
                root.after_cancel(cap["pulse"])
            except Exception:
                pass
            cap["pulse"] = None
        ctx["suspend"](False)
        if d:
            if msg:
                d(msg)
                def _restore():
                    try:
                        if not cap["which"]:
                            d()
                    except Exception:
                        pass       # Chip existiert nach Theme-Wechsel nicht mehr
                root.after(1400, _restore)
            else:
                d()

    def on_keypress(e):
        if not cap["which"]:
            return
        r = _keysym_to_hotkey(e)
        if r is None:                      # nur Modifier -> weiter warten
            return
        if r == "__clear__":
            if cap["clear_ok"]:
                ctx["set_hotkey"](cap["which"], "")
                end_capture()
            else:
                end_capture("Entf hier nicht möglich")
            return
        if r == "__invalid__":
            end_capture("Taste nicht unterstützt")
            return
        if "+" not in r and len(r) == 1:   # nackter Buchstabe = zu gefaehrlich
            end_capture("nur mit Strg/Alt kombinieren")
            return
        err = ctx["set_hotkey"](cap["which"], r)
        end_capture("ungültig" if err else None)
        rebuild()                          # Untertitel + Chips aktualisieren

    root.bind("<KeyPress>", on_keypress)

    def nice_key(v):
        return (v or "").replace("<", "").replace(">", "").upper()

    # ---- Fensterinhalt (pro Theme neu aufgebaut) -----------------------------
    def rebuild():
        if cap["which"]:
            end_capture()

        pal = THEMES.get(cfg.get("theme") or "mix", THEMES["mix"])
        BGC = pal["bg"]

        # Schriften: Familjen Grotesk/Lora falls geladen, sonst Segoe UI
        if pal["serif"] and "Familjen Grotesk" in fams:
            body = "Familjen Grotesk"
        elif not pal["serif"] and "Segoe UI Variable Text" in fams:
            body = "Segoe UI Variable Text"
        else:
            body = "Segoe UI"
        F, FS, FB = (body, 11), (body, 9), (body, 10)
        if pal["serif"] and "Lora" in fams:
            FT = ("Lora", 14)              # die Datei ist SemiBold
        elif "Segoe UI Variable Display" in fams and not pal["serif"]:
            FT = ("Segoe UI Variable Display", 13, "bold")
        else:
            FT = (body, 13, "bold")

        root.configure(bg=pal["border"])   # 1px-Rahmen um die Bubble
        if holder["content"]:
            holder["content"].destroy()
        # Inhalt liegt in einem Canvas, damit das Fenster auf kleinen Bildschirmen
        # (Laptop, 1080p) per Mausrad scrollbar bleibt statt abgeschnitten zu werden.
        shell = tk.Frame(root, bg=BGC)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        scroller = tk.Canvas(shell, bg=BGC, highlightthickness=0, bd=0)
        scroller.pack(fill="both", expand=True)
        content = tk.Frame(scroller, bg=BGC)
        scroller.create_window(0, 0, window=content, anchor="nw", width=WW - 2)
        holder["content"] = shell
        holder["scroller"] = scroller
        if not holder.get("wheel_bound"):
            holder["wheel_bound"] = True
            def on_wheel(e):
                sc = holder.get("scroller")
                if sc is not None and holder.get("scrollable"):
                    sc.yview_scroll(-1 if e.delta > 0 else 1, "units")
            root.bind_all("<MouseWheel>", on_wheel)

        # -- Bausteine --------------------------------------------------------
        def section(text, first=False):
            if not first:
                tk.Frame(content, bg=pal["divider"], height=1
                         ).pack(fill="x", padx=20, pady=(12, 0))
            tk.Label(content, text=t(text), bg=BGC, fg=pal["sect"],
                     font=(body, 8, "bold"), anchor="w"
                     ).pack(fill="x", padx=20, pady=((4 if first else 10), 0))

        def hint(text):
            tk.Label(content, text=t(text), bg=BGC, fg=pal["subtle"], font=FS,
                     anchor="w").pack(fill="x", padx=22)

        def toggle_row(text, get, set_cb):
            row = tk.Frame(content, bg=BGC)
            row.pack(fill="x", padx=20, pady=4)
            lbl = tk.Label(row, text=t(text), bg=BGC, fg=pal["text"], font=F,
                           anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)
            TW, TH = 38, 22
            R, KR = TH // 2, TH // 2 - 3
            c = tk.Canvas(row, width=TW, height=TH, bg=BGC,
                          highlightthickness=0, bd=0, cursor="hand2")
            c.pack(side="right")
            def render(x, on):
                c.delete("all")
                c._imgs = [_pill(c, TW, TH, R, pal["tog_on"] if on else pal["tog_off"],
                                 knob=(x, KR, "#ffffff"))]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
            def knob_x(on):
                return TW - R if on else R
            def slide(frm, to, on, i=0, n=4):
                x = frm + (to - frm) * (i + 1) / n
                render(x, on)
                if i + 1 < n:
                    c.after(14, slide, frm, to, on, i + 1, n)
            def click(_e=None):
                on = not bool(get())
                set_cb(on)
                slide(knob_x(not on), knob_x(on), on)
            c.bind("<Button-1>", click)
            lbl.bind("<Button-1>", click)
            render(knob_x(bool(get())), bool(get()))

        def select_row(text_get, options, on_pick):
            c = tk.Canvas(content, height=34, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=4)
            menu = tk.Menu(root, tearoff=0, bg=pal["field_bg"], fg=pal["text"],
                           activebackground=pal["chip_hot"],
                           activeforeground="white", bd=0, font=FB)
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = WW - 42
                c._imgs = [_pill(c, w, 34, 8, pal["field_bg"], outline=pal["field_border"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                txt = t(text_get())
                if len(txt) > 34:
                    txt = txt[:33] + "…"
                c.create_text(14, 17, anchor="w", text=txt, fill=pal["text"], font=FB)
                c.create_text(w - 14, 17, anchor="e", text="⌄", fill=pal["subtle"],
                              font=(body, 10, "bold"))
            for opt in options:
                menu.add_command(label=t(opt), command=lambda o=opt: (on_pick(o), draw()))
            c.bind("<Button-1>", lambda e: menu.tk_popup(c.winfo_rootx() + 8,
                                                         c.winfo_rooty() + 36))
            c.bind("<Configure>", draw)
            draw()

        def pill_button(text, cmd):
            c = tk.Canvas(content, height=36, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=(14, 16))
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = WW - 42
                c._imgs = [_pill(c, w, 36, 8, pal["btn_bg"], outline=pal["btn_border"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                c.create_text(w / 2, 18, text=t(text), fill=pal["btn_text"],
                              font=(body, 10, "bold"))
            c.bind("<Configure>", draw)
            c.bind("<Button-1>", lambda e: cmd())
            draw()

        def hotkey_row(text, which, clear_ok=False):
            row = tk.Frame(content, bg=BGC)
            row.pack(fill="x", padx=20, pady=4)
            tk.Label(row, text=t(text), bg=BGC, fg=pal["text"], font=F,
                     anchor="w").pack(side="left", fill="x", expand=True)
            CW, CH = 124, 28
            c = tk.Canvas(row, width=CW, height=CH, bg=BGC,
                          highlightthickness=0, bd=0, cursor="hand2")
            c.pack(side="right")
            def draw(txt=None, hot=False):
                c.delete("all")
                c._imgs = [_pill(c, CW, CH, 7, pal["chip_bg"],
                                 outline=pal["chip_hot"] if hot else pal["chip_border"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                label = t(txt) if txt else (nice_key(cfg.get(which)) or t("aus"))
                # Meldungen ("nur mit Strg/Alt ...") kleiner, sonst passt es nicht
                fnt = (body, 8) if txt else (body, 9, "bold")
                c.create_text(CW / 2, CH / 2, text=label,
                              fill=pal["chip_hot"] if hot else pal["chip_text"],
                              font=fnt)
            def pulse(on=True):
                if cap["which"] != which:
                    return
                c.delete("all")
                c._imgs = [_pill(c, CW, CH, 7, pal["chip_bg"],
                                 outline=pal["chip_hot"] if on else pal["chip_hot2"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                c.create_text(CW / 2, CH / 2, text=t("Taste drücken …"),
                              fill=pal["chip_hot"] if on else pal["chip_hot2"],
                              font=(body, 9))
                cap["pulse"] = root.after(550, pulse, not on)
            def click(_e=None):
                if cap["which"]:
                    return
                cap["which"] = which
                cap["redraw"] = draw
                cap["clear_ok"] = clear_ok
                ctx["suspend"](True)      # globalen Hotkey solange stummschalten
                pulse()
                root.focus_force()
            c.bind("<Button-1>", click)
            draw()

        def meter_row():
            row = tk.Frame(content, bg=BGC)
            row.pack(fill="x", padx=22, pady=(2, 0))
            tk.Label(row, text=t("Pegel"), bg=BGC, fg=pal["subtle"],
                     font=(body, 8)).pack(side="left")
            c = tk.Canvas(row, height=5, bg=BGC, highlightthickness=0, bd=0)
            c.pack(side="left", fill="x", expand=True, padx=(10, 0))
            def draw(level):
                if not c.winfo_exists():
                    return
                w = c.winfo_width()
                if w < 10:
                    return
                if pal["meter"] == "ampel":
                    col = next(col for th, col in AMPEL if level >= th)
                else:
                    col = pal["meter"]
                c.delete("all")
                c._imgs = [_pill(c, w, 5, 2, pal["meter_bg"])]
                fw = max(5, int(w * level))
                c._imgs.append(_pill(c, fw, 5, 2, col))
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                c.create_image(0, 0, anchor="nw", image=c._imgs[1])
            holder["meter_draw"] = draw

        def seg_row():
            order = ["hell", "claude", "mix"]
            c = tk.Canvas(content, height=30, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=4)
            cur = cfg.get("theme") or "mix"
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = WW - 42
                c._imgs = [_pill(c, w, 30, 9, pal["seg_bg"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                seg_w = (w - 6) / 3
                idx = order.index(cur)
                c._imgs.append(_pill(c, int(seg_w), 24, 7, "#ffffff",
                                     outline=pal["field_border"]))
                c.create_image(3 + int(idx * seg_w), 3, anchor="nw", image=c._imgs[1])
                for i, key in enumerate(order):
                    active = (key == cur)
                    c.create_text(3 + (i + 0.5) * seg_w, 15,
                                  text=t(THEMES[key]["label"]),
                                  fill=pal["text"] if active else pal["subtle"],
                                  font=(body, 9, "bold" if active else "normal"))
            def click(e):
                w = c.winfo_width()
                idx = min(2, max(0, int((e.x - 3) / ((w - 6) / 3))))
                key = order[idx]
                if key != (cfg.get("theme") or "mix"):
                    cfg["theme"] = key
                    save()
                    rebuild()
            c.bind("<Button-1>", click)
            c.bind("<Configure>", draw)
            draw()

        def cfg_toggle(key):
            return (lambda: cfg.get(key),
                    lambda v: (cfg.__setitem__(key, bool(v)), save()))

        # -- Kopf: Titel, Schliessen, Untertitel, Verschieben -------------------
        head = tk.Frame(content, bg=BGC)
        head.pack(fill="x", padx=(20, 10), pady=(12, 0))
        title = tk.Label(head, text="⚡ Blitztext", bg=BGC, fg=pal["text"],
                         font=FT, anchor="w")
        title.pack(side="left")
        close = tk.Canvas(head, width=34, height=34, bg=BGC,
                          highlightthickness=0, bd=0, cursor="hand2")
        close.pack(side="right")
        def close_draw(hover=False):
            close.delete("all")
            if hover:
                close._imgs = [_circle(close, 34, pal["close_hover"])]
                close.create_image(0, 0, anchor="nw", image=close._imgs[0])
            close.create_text(17, 17, text="✕",
                              fill=pal["text"] if hover else pal["subtle"],
                              font=(body, 12))
        close.bind("<Button-1>", lambda e: root.destroy())
        close.bind("<Enter>", lambda e: close_draw(True))
        close.bind("<Leave>", lambda e: close_draw(False))
        close_draw()

        hk = nice_key(cfg.get("hotkey")) or "?"
        hk2 = nice_key(cfg.get("hotkey_second"))
        lang2 = next((l for l, c in LANGS if c == cfg.get("second_language")),
                     cfg.get("second_language") or "")
        parts = [f"{t('Hotkey')} {hk}"] + ([f"{hk2} = {t(lang2)}"] if hk2 else []) \
                + [t("Esc = verwerfen")]
        sub = tk.Label(content, text="  ·  ".join(parts), bg=BGC,
                       fg=pal["subtle"], font=FS, anchor="w")
        sub.pack(fill="x", padx=21)

        def drag_start(e):
            root._dx = e.x_root - root.winfo_x()
            root._dy = e.y_root - root.winfo_y()
        def drag_move(e):
            root.geometry(f"+{e.x_root - root._dx}+{e.y_root - root._dy}")
        for w in (head, title, sub):
            w.bind("<Button-1>", drag_start)
            w.bind("<B1-Motion>", drag_move)

        # -- Inhalt --------------------------------------------------------------
        section("HOTKEYS", first=True)
        hotkey_row("Aufnahme", "hotkey")
        hotkey_row("Zweitsprache (einmalig)", "hotkey_second", clear_ok=True)
        hint("klicken, dann neue Taste drücken (Entf = aus)")
        code_to_label2 = {c: l for l, c in LANGS if c}
        def lang2_pick(val):
            cfg["second_language"] = dict(LANGS)[val]
            save()
            rebuild()
        select_row(lambda: code_to_label2.get(cfg.get("second_language") or "en", "Englisch"),
                   [l for l, c in LANGS if c], lang2_pick)
        hint("Sprache, die der Zweit-Hotkey für ein Diktat nutzt")

        section("AUFNAHME")
        toggle_row("Gedrückt halten (Push-to-Talk)", *cfg_toggle("push_to_talk"))
        hint("Hotkey halten = aufnehmen · loslassen = fertig")
        toggle_row("Ton bei Start/Stopp", *cfg_toggle("beep"))

        section("MIKROFON")
        AUTO_MIC = "Automatisch (System-Standard)"
        devices = [AUTO_MIC] + list(ctx["devices"]())
        cur_mic = cfg.get("input_device")
        if cur_mic and cur_mic not in devices:
            devices.append(cur_mic)          # gespeichertes, gerade getrenntes Geraet
        def mic_pick(val):
            cfg["input_device"] = None if val == AUTO_MIC else val
            save()
            meter_start()
        select_row(lambda: cfg.get("input_device") or AUTO_MIC, devices, mic_pick)
        meter_row()

        section("MODELL")
        label_to_model = dict(MODELS)
        model_to_label = {m: l for l, m in MODELS}
        def model_pick(val):
            neu = label_to_model[val]
            if neu != cfg.get("model"):
                cfg["model"] = neu
                save()
                ctx["reload_model"]()      # lädt im Hintergrund neu (Icon grau)
        select_row(lambda: model_to_label.get(cfg.get("model"), cfg.get("model") or "?"),
                   [l for l, _ in MODELS], model_pick)
        hint("Wechsel lädt das Modell neu · beim ersten Mal Download")

        section("SPRACHE")
        code_to_label = {c: l for l, c in LANGS}
        def lang_pick(val):
            cfg["language"] = dict(LANGS)[val]
            save()
        select_row(lambda: code_to_label.get(cfg.get("language") or "", "Automatisch"),
                   [l for l, _ in LANGS], lang_pick)
        toggle_row("Ins Englische übersetzen", *cfg_toggle("translate_to_english"))

        section("AUSGABE")
        toggle_row("Automatisch einfügen", *cfg_toggle("paste"))
        toggle_row("Automatisch Enter (absenden)", *cfg_toggle("auto_enter"))
        toggle_row("Tippen statt Einfügen", *cfg_toggle("type_instead_of_paste"))
        toggle_row("Sprachbefehle", *cfg_toggle("voice_commands"))
        hint("»neue Zeile« / »neuer Absatz« sprechen = Umbruch")

        section("SYSTEM")
        toggle_row("Mit Windows starten",
                   lambda: ctx["autostart_get"](),
                   lambda v: ctx["autostart_set"](bool(v)))
        toggle_row("Status-HUD anzeigen", *cfg_toggle("overlay"))
        hint("wirkt nach Neustart der App")
        toggle_row("Nach Updates suchen", *cfg_toggle("update_check"))
        hint("fragt gelegentlich bei GitHub nach einer neuen Version")

        section("DARSTELLUNG")
        seg_row()
        UI_LANGS = [("Automatisch", "auto"), ("Deutsch", "de"), ("English", "en")]
        ui_to_label = {c: l for l, c in UI_LANGS}
        def ui_pick(val):
            cfg["ui_language"] = dict(UI_LANGS)[val]
            save()
            set_language(cfg["ui_language"])
            if ctx.get("refresh_tray"):
                ctx["refresh_tray"]()
            rebuild()
        select_row(lambda: ui_to_label.get(cfg.get("ui_language") or "auto", "Automatisch"),
                   [l for l, _ in UI_LANGS], ui_pick)
        hint("Oberfläche")

        pill_button("Wörterbuch bearbeiten", lambda: ctx["open_vocab"]())

        # -- Groesse + Position: erstmalig rechts unten (beim Tray), danach
        # bleibt die Unterkante, wo der Nutzer das Fenster hingezogen hat ------
        root.update_idletasks()
        voll = content.winfo_reqheight() + 2
        wh = min(voll, root.winfo_screenheight() - 110)
        holder["scrollable"] = voll > wh
        scroller.configure(scrollregion=(0, 0, WW - 2, voll - 2))
        scroller.configure(yscrollincrement=30)
        if holder.get("placed"):
            x = root.winfo_x()
            y = root.winfo_y() + root.winfo_height() - wh
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x, y = sw - WW - 20, sh - wh - 80
            holder["placed"] = True
        root.geometry(f"{WW}x{wh}+{x}+{y}")

    rebuild()
    _round_corners(root)
    meter_start()
    meter_tick()

    # sanft einblenden: Fade + kurzes Hochgleiten
    root.attributes("-alpha", 0.0)
    root.deiconify()
    fx, fy = root.winfo_x(), root.winfo_y()
    def fade_in(i=0, n=10):
        if not root.winfo_exists():
            return
        a = (i + 1) / n
        root.attributes("-alpha", a)
        root.geometry(f"+{fx}+{fy + int(14 * (1 - a))}")
        if i + 1 < n:
            root.after(14, fade_in, i + 1, n)
    fade_in()

    def on_escape(_e):
        if cap["which"]:
            end_capture()      # Esc bricht nur die Hotkey-Aufnahme ab
        else:
            root.destroy()
    root.bind("<Escape>", on_escape)
    try:
        root.focus_force()
    except Exception:
        pass

    try:
        root.mainloop()
    finally:
        meter_stop()
