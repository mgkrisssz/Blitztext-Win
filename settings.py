"""
Einstellungsfenster fuer Blitztext (Doppelklick auf das Tray-Icon).

Design: randlose helle "Bubble" mit runden Ecken (DWM), flache Flaechen,
drei umschaltbare Stile (cfg["theme"]):
  "mix"    - weiss, Lora-Titel, gut lesbare Windows-Schrift, Terrakotta/Gruen
  "petrol" - leichtes Gruengrau mit Petrol-Akzent (Standard)
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

# Kleine Erklaerungen beim Darueberfahren mit der Maus (Schluessel = Beschriftung der Zeile)
TIPS = {
    'Aufnahme': 'Startet und beendet die Aufnahme.',
    'Zweitsprache (einmalig)': 'Diktiert einmalig in der Zweitsprache.',
    'Zweitsprache-Auswahl': 'Sprache des Zweit-Hotkeys.',
    'Gedrückt halten (Push-to-Talk)': 'Halten = aufnehmen, loslassen = fertig.',
    'Ton bei Start/Stopp': 'Piepton bei Start und Ende.',
    'Mikrofon-Auswahl': 'Der Pegel darunter muss beim Sprechen ausschlagen.',
    'Modell-Auswahl': 'Größer = genauer, aber langsamer.',
    'Sprache-Auswahl': 'Die Sprache, in der du sprichst.',
    'Ins Englische übersetzen': 'Schreibt alles direkt auf Englisch.',
    'Automatisch einfügen': 'Fügt den Text am Cursor ein.',
    'Zwischenablage zurücksetzen': 'Dein vorher Kopiertes bleibt erhalten.',
    'Automatisch Enter (absenden)': 'Drückt nach dem Einfügen Enter.',
    'Tippen statt Einfügen': 'Wie von Hand getippt. Nur nötig, wenn Einfügen nicht klappt.',
    'Tempo-Auswahl': 'Wie schnell der Text beim Tippen erscheint.',
    'Sprachbefehle': '„neue Zeile“ wird zum Umbruch.',
    'Mit Windows starten': 'Startet mit deiner Anmeldung.',
    'Status-HUD anzeigen': 'Anzeige am Bildschirmrand beim Aufnehmen.',
    'Nach Updates suchen': 'Fragt bei GitHub nach einer neuen Version.',
    'Oberfläche-Auswahl': 'Sprache der Menüs.',
    'Wörterbuch bearbeiten': 'Namen und feste Ersetzungen (falsch => richtig).',
    'Neu starten': 'Beendet Blitztext und startet es neu.',
}

# Ampel-Farben fuer den Mikrofonpegel (Stil "mix")
AMPEL = [(0.88, "#c53929"), (0.70, "#d9930d"), (0.0, "#2d8659")]

THEMES = {
    "mix": dict(
        label="Mix",
        bg="#ffffff", border="#e5e4de", text="#2b2a25", subtle="#6b695e",
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
        bg="#faf9f5", border="#e8e5da", text="#35322a", subtle="#6c6858",
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
        bg="#ffffff", border="#e4e6ea", text="#1b1e24", subtle="#656b75",
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
    "petrol": dict(
        label="Petrol",
        bg="#f6f8f8", border="#d9e3e1", text="#1d2b29", subtle="#586a66",
        divider="#e4ebea", sect="#0e7c6b",
        chip_bg="#ffffff", chip_border="#d0dcda", chip_text="#2c3d3a",
        chip_hot="#0e7c6b", chip_hot2="#4aa798",
        tog_off="#b3c6c2", tog_on="#0e7c6b",
        field_bg="#ffffff", field_border="#d0dcda",
        btn_bg="#0e7c6b", btn_border="#0e7c6b", btn_text="#ffffff",
        seg_bg="#e6eeed",
        meter_bg="#e1eae8", meter="#0e7c6b",
        close_hover="#e9f0ef",
        serif=True,
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
    autostart_get, autostart_set, open_vocab, set_hotkey, reload_model, restart, suspend,
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

    WW = 660                 # Fensterbreite
    SB_W = 170               # Breite der Seitenleiste links
    PW = WW - 2 - SB_W       # Breite der Einstellungsseite rechts
    WH = 480                 # Fensterhoehe (wird auf kleinen Bildschirmen gekuerzt)
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

        pal = THEMES.get(cfg.get("theme") or "petrol", THEMES["petrol"])
        BGC = pal["bg"]

        # Schriften: Fliesstext in der klaren Windows-Schrift (Familjen Grotesk war schwer
        # zu lesen); nur der Titel nutzt bei den Serif-Stilen die Schrift Lora
        if "Segoe UI Variable Text" in fams:
            body = "Segoe UI Variable Text"
        else:
            body = "Segoe UI"
        F, FS, FB = (body, 11), (body, 10), (body, 10)
        if pal["serif"] and "Lora" in fams:
            FT = ("Lora", 14)              # die Datei ist SemiBold
        elif "Segoe UI Variable Display" in fams and not pal["serif"]:
            FT = ("Segoe UI Variable Display", 13, "bold")
        else:
            FT = (body, 13, "bold")

        root.configure(bg=pal["border"])   # 1px-Rahmen um die Bubble
        if holder.get("popup_close"):
            holder["popup_close"]()
        if holder["content"]:
            holder["content"].destroy()
        # Aufbau: oben der Kopf, darunter links die Seitenleiste und rechts die gewaehlte
        # Einstellungsseite (in einem Canvas, damit sie auf kleinen Bildschirmen scrollt).
        shell = tk.Frame(root, bg=BGC)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        header_f = tk.Frame(shell, bg=BGC)
        header_f.pack(fill="x")
        body_f = tk.Frame(shell, bg=BGC)
        body_f.pack(fill="both", expand=True)
        side = tk.Frame(body_f, bg=pal["seg_bg"], width=SB_W)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        right = tk.Frame(body_f, bg=BGC)
        right.pack(side="left", fill="both", expand=True)
        scroller = tk.Canvas(right, bg=BGC, highlightthickness=0, bd=0)
        scroller.pack(fill="both", expand=True)
        content = None                      # aktuelle Seite (wird in show_page gesetzt)
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
                     anchor="w", justify="left", wraplength=PW - 48).pack(fill="x", padx=22)

        def attach_tip(widgets, key):
            """Kleine Erklaerung, wenn die Maus kurz ueber der Zeile verweilt."""
            tip = TIPS.get(key)
            if not tip:
                return
            st = {"job": None, "win": None}

            def weg(_e=None):
                if st["job"]:
                    try:
                        root.after_cancel(st["job"])
                    except Exception:
                        pass
                    st["job"] = None
                if st["win"]:
                    try:
                        st["win"].destroy()
                    except Exception:
                        pass
                    st["win"] = None

            def zeigen(x, y):
                st["job"] = None
                tw = tk.Toplevel(root)
                tw.overrideredirect(True)
                tw.attributes("-topmost", True)
                tw.configure(bg=pal["text"])
                tk.Label(tw, text=t(tip), bg=pal["text"], fg="#ffffff",
                         font=("Segoe UI", 11), justify="left", wraplength=260,
                         padx=16, pady=9).pack()
                _round_corners(tw)                     # runde "Blase"
                tw.update_idletasks()
                bw, bh = tw.winfo_reqwidth(), tw.winfo_reqheight()
                px = min(x + 14, root.winfo_screenwidth() - bw - 8)
                py = y + 20
                if py + bh > root.winfo_screenheight() - 40:
                    py = y - bh - 12
                tw.geometry(f"+{max(0, px)}+{py}")
                st["win"] = tw

            def planen(e):
                weg()
                st["job"] = root.after(450, zeigen, e.x_root, e.y_root)

            for wdg in widgets:
                wdg.bind("<Enter>", planen, add="+")
                wdg.bind("<Leave>", weg, add="+")
                wdg.bind("<Button-1>", weg, add="+")

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
            attach_tip((lbl, c), text)

        def select_row(text_get, options, on_pick, tip=None):
            c = tk.Canvas(content, height=34, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=4)
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = PW - 42
                c._imgs = [_pill(c, w, 34, 8, pal["field_bg"], outline=pal["field_border"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                txt = t(text_get())
                if len(txt) > 34:
                    txt = txt[:33] + "…"
                c.create_text(14, 17, anchor="w", text=txt, fill=pal["text"], font=FB)
                c.create_line(w - 25, 15, w - 20, 20, w - 15, 15, fill=pal["subtle"], width=2,
                              capstyle="round", joinstyle="round")
            def open_popup(_e=None):
                """Eigenes, zum Theme passendes Auswahlfenster (statt des Windows-Menues)."""
                if holder.get("popup_close"):
                    holder["popup_close"]()
                    return
                ROW, MAXROWS = 34, 7
                top = tk.Toplevel(root)
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                top.configure(bg=pal["field_border"])          # 1px-Rahmen
                w = c.winfo_width()
                rows = min(len(options), MAXROWS)
                h = rows * ROW + 8
                x, y = c.winfo_rootx(), c.winfo_rooty() + 38
                if y + h > root.winfo_screenheight() - 40:       # kein Platz unten -> nach oben
                    y = c.winfo_rooty() - h - 4
                top.geometry(f"{w}x{h + 2}+{x}+{y}")

                body_f = tk.Frame(top, bg=pal["field_bg"])
                body_f.pack(fill="both", expand=True, padx=1, pady=1)
                cv = tk.Canvas(body_f, bg=pal["field_bg"], highlightthickness=0, bd=0)
                cv.pack(fill="both", expand=True)
                lst = tk.Frame(cv, bg=pal["field_bg"])
                cv.create_window(0, 0, window=lst, anchor="nw", width=w - 2)
                current = text_get()

                def schliessen(_e=None):
                    holder["popup_close"] = None
                    try:
                        top.grab_release()
                    except Exception:
                        pass
                    try:
                        top.destroy()
                    except Exception:
                        pass

                def waehlen(o):
                    schliessen()
                    on_pick(o)
                    draw()

                for opt in options:
                    aktiv = (opt == current)
                    row = tk.Frame(lst, bg=pal["field_bg"], height=ROW, cursor="hand2")
                    row.pack(fill="x", padx=4, pady=(4 if opt == options[0] else 0, 0))
                    row.pack_propagate(False)
                    lab = tk.Label(row, text=t(opt), bg=pal["field_bg"], fg=pal["text"],
                                   font=(body, 10, "bold" if aktiv else "normal"), anchor="w")
                    lab.pack(side="left", fill="both", expand=True, padx=(10, 0))
                    tick = tk.Label(row, text="✓" if aktiv else "", bg=pal["field_bg"],
                                    fg=pal["chip_hot"], font=(body, 10, "bold"))
                    tick.pack(side="right", padx=(0, 10))
                    def hover(on, row=row, lab=lab, tick=tick):
                        col = pal["seg_bg"] if on else pal["field_bg"]
                        for wdg in (row, lab, tick):
                            wdg.configure(bg=col)
                    for wdg in (row, lab, tick):
                        wdg.bind("<Enter>", lambda e, hv=hover: hv(True))
                        wdg.bind("<Leave>", lambda e, hv=hover: hv(False))
                        wdg.bind("<Button-1>", lambda e, o=opt: waehlen(o))

                lst.update_idletasks()
                gesamt = lst.winfo_reqheight() + 4
                cv.configure(scrollregion=(0, 0, w - 2, gesamt))
                if len(options) > MAXROWS:                      # lange Liste: Mausrad scrollt
                    def rad(e):
                        cv.yview_scroll(-1 if e.delta > 0 else 1, "units")
                    top.bind("<MouseWheel>", rad)
                    cv.configure(yscrollincrement=ROW)
                    # aktuelle Auswahl sichtbar machen
                    if current in options:
                        idx = options.index(current)
                        cv.yview_moveto(max(0, (idx - 2) * ROW) / max(gesamt, 1))

                # Klick ausserhalb oder Esc schliesst
                def klick(e):
                    if not (top.winfo_rootx() <= e.x_root < top.winfo_rootx() + top.winfo_width()
                            and top.winfo_rooty() <= e.y_root < top.winfo_rooty() + top.winfo_height()):
                        schliessen()
                top.bind("<Button-1>", klick, add="+")
                top.bind("<Escape>", schliessen)
                holder["popup_close"] = schliessen
                _round_corners(top)
                try:
                    top.grab_set()
                    top.focus_force()
                except Exception:
                    pass
            c.bind("<Button-1>", open_popup)
            attach_tip((c,), tip)
            c.bind("<Configure>", draw)
            draw()

        def pill_button(text, cmd, pady=(14, 16), secondary=False):
            c = tk.Canvas(content, height=36, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=pady)
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = PW - 42
                if secondary:       # zurueckhaltender Zweitknopf: heller Grund, Rahmen
                    bg, rand, txt = pal["chip_bg"], pal["chip_border"], pal["chip_text"]
                else:
                    bg, rand, txt = pal["btn_bg"], pal["btn_border"], pal["btn_text"]
                c._imgs = [_pill(c, w, 36, 8, bg, outline=rand)]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                c.create_text(w / 2, 18, text=t(text), fill=txt,
                              font=(body, 10, "bold"))
            c.bind("<Configure>", draw)
            c.bind("<Button-1>", lambda e: cmd())
            attach_tip((c,), text)
            draw()

        def hotkey_row(text, which, clear_ok=False):
            row = tk.Frame(content, bg=BGC)
            row.pack(fill="x", padx=20, pady=4)
            hl = tk.Label(row, text=t(text), bg=BGC, fg=pal["text"], font=F, anchor="w")
            hl.pack(side="left", fill="x", expand=True)
            attach_tip((hl,), text)
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
            order = ["hell", "claude", "mix", "petrol"]
            n_seg = len(order)
            c = tk.Canvas(content, height=30, bg=BGC, highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=20, pady=4)
            cur = cfg.get("theme") or "petrol"
            def draw(_e=None):
                c.delete("all")
                w = c.winfo_width()
                if w < 10:
                    w = PW - 42
                c._imgs = [_pill(c, w, 30, 9, pal["seg_bg"])]
                c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                seg_w = (w - 6) / n_seg
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
                idx = min(n_seg - 1, max(0, int((e.x - 3) / ((w - 6) / n_seg))))
                key = order[idx]
                if key != (cfg.get("theme") or "petrol"):
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
        head = tk.Frame(header_f, bg=BGC)
        head.pack(fill="x", padx=(20, 10), pady=(12, 0))
        from logo import blitz_icon
        # Logo in der Akzentfarbe des gewaehlten Stils (Petrol -> petrolfarbener Blitz)
        akzent = pal["chip_hot"].lstrip("#")
        akzent_rgba = tuple(int(akzent[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        logo_img = ImageTk.PhotoImage(blitz_icon(akzent_rgba, 26), master=head)
        title = tk.Label(head, text=" Blitztext", image=logo_img, compound="left",
                         bg=BGC, fg=pal["text"], font=FT, anchor="w")
        title._logo = logo_img                  # Referenz halten (sonst raeumt Tk das Bild weg)
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
        sub = tk.Label(header_f, text="  ·  ".join(parts), bg=BGC,
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

        tk.Frame(header_f, bg=pal["divider"], height=1).pack(fill="x", pady=(10, 0))

        # -- Seiten ------------------------------------------------------------------
        def seite_aufnahme():
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
                       [l for l, c in LANGS if c], lang2_pick, tip="Zweitsprache-Auswahl")
            hint("Sprache, die der Zweit-Hotkey für ein Diktat nutzt")

            section("AUFNAHME")
            toggle_row("Gedrückt halten (Push-to-Talk)", *cfg_toggle("push_to_talk"))
            hint("Hotkey halten = aufnehmen · loslassen = fertig")
            toggle_row("Ton bei Start/Stopp", *cfg_toggle("beep"))

        def seite_erkennung():
            section("MIKROFON", first=True)
            AUTO_MIC = "Automatisch (System-Standard)"
            devices = [AUTO_MIC] + list(ctx["devices"]())
            cur_mic = cfg.get("input_device")
            if cur_mic and cur_mic not in devices:
                devices.append(cur_mic)          # gespeichertes, gerade getrenntes Geraet
            def mic_pick(val):
                cfg["input_device"] = None if val == AUTO_MIC else val
                save()
                meter_start()
            select_row(lambda: cfg.get("input_device") or AUTO_MIC, devices, mic_pick,
                       tip="Mikrofon-Auswahl")
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
                       [l for l, _ in MODELS], model_pick, tip="Modell-Auswahl")
            hint("Wechsel lädt neu · beim ersten Mal Download")

            section("SPRACHE")
            code_to_label = {c: l for l, c in LANGS}
            def lang_pick(val):
                cfg["language"] = dict(LANGS)[val]
                save()
            select_row(lambda: code_to_label.get(cfg.get("language") or "", "Automatisch"),
                       [l for l, _ in LANGS], lang_pick, tip="Sprache-Auswahl")
            toggle_row("Ins Englische übersetzen", *cfg_toggle("translate_to_english"))
            pill_button("Wörterbuch bearbeiten", lambda: ctx["open_vocab"](), pady=(16, 14))

        def seite_ausgabe():
            section("AUSGABE", first=True)
            toggle_row("Automatisch einfügen", *cfg_toggle("paste"))
            toggle_row("Automatisch Enter (absenden)", *cfg_toggle("auto_enter"))
            toggle_row("Tippen statt Einfügen", *cfg_toggle("type_instead_of_paste"))
            TEMPI = [("Tipp-Tempo: Sofort", "instant"), ("Tipp-Tempo: Schnell", "fast"),
                     ("Tipp-Tempo: Normal", "normal"), ("Tipp-Tempo: Langsam", "slow")]
            tempo_to_label = {c: l for l, c in TEMPI}
            def tempo_pick(val):
                cfg["typing_speed"] = dict(TEMPI)[val]
                save()
            select_row(lambda: tempo_to_label.get(cfg.get("typing_speed") or "normal", TEMPI[2][0]),
                       [l for l, _ in TEMPI], tempo_pick, tip="Tempo-Auswahl")
            toggle_row("Zwischenablage zurücksetzen", *cfg_toggle("restore_clipboard"))
            toggle_row("Sprachbefehle", *cfg_toggle("voice_commands"))

        def seite_system():
            section("SYSTEM", first=True)
            toggle_row("Mit Windows starten",
                       lambda: ctx["autostart_get"](),
                       lambda v: ctx["autostart_set"](bool(v)))
            toggle_row("Status-HUD anzeigen", *cfg_toggle("overlay"))
            hint("wirkt nach Neustart der App")
            toggle_row("Nach Updates suchen", *cfg_toggle("update_check"))

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
                       [l for l, _ in UI_LANGS], ui_pick, tip="Oberfläche-Auswahl")
            hint("Sprache der Oberfläche")
            if ctx.get("restart"):
                pill_button("Neu starten", lambda: ctx["restart"](), pady=(18, 14), secondary=True)

        PAGES = {"Aufnahme": seite_aufnahme, "Erkennung": seite_erkennung,
                 "Ausgabe": seite_ausgabe, "System": seite_system}
        nav_draw = {}

        def show_page(name):
            nonlocal content
            if cap["which"]:
                end_capture()
            if holder.get("popup_close"):
                holder["popup_close"]()
            holder["page"] = name
            holder["meter_draw"] = None
            scroller.delete("all")
            for w_ in list(scroller.winfo_children()):
                w_.destroy()
            content = tk.Frame(scroller, bg=BGC)
            scroller.create_window(0, 0, window=content, anchor="nw", width=PW)
            scroller.yview_moveto(0)
            PAGES[name]()
            for redraw in nav_draw.values():
                redraw()
            root.update_idletasks()
            voll = content.winfo_reqheight()
            scroller.configure(scrollregion=(0, 0, PW, voll), yscrollincrement=30)
            holder["scrollable"] = voll > scroller.winfo_height()

        # -- Seitenleiste ---------------------------------------------------------------
        tk.Frame(side, bg=pal["seg_bg"], height=10).pack()
        for name in PAGES:
            c = tk.Canvas(side, height=38, bg=pal["seg_bg"], highlightthickness=0,
                          bd=0, cursor="hand2")
            c.pack(fill="x", padx=10, pady=(0, 4))
            def draw_nav(_e=None, c=c, name=name):
                c.delete("all")
                w_ = c.winfo_width()
                if w_ < 10:
                    w_ = SB_W - 20
                aktiv = holder.get("page") == name
                if aktiv:
                    c._imgs = [_pill(c, w_, 38, 9, "#ffffff", outline=pal["field_border"])]
                    c.create_image(0, 0, anchor="nw", image=c._imgs[0])
                c.create_text(16, 19, anchor="w", text=t(name),
                              fill=pal["text"] if aktiv else pal["subtle"],
                              font=(body, 11, "bold" if aktiv else "normal"))
            nav_draw[name] = draw_nav
            c.bind("<Configure>", draw_nav)
            c.bind("<Button-1>", lambda e, name=name: show_page(name))
            draw_nav()
        if ctx.get("version"):
            tk.Label(side, text="v" + str(ctx["version"]), bg=pal["seg_bg"], fg=pal["subtle"],
                     font=(body, 9)).pack(side="bottom", pady=10)

        # -- Groesse + Position: erstmalig rechts unten (beim Tray), danach
        # bleibt die Unterkante, wo der Nutzer das Fenster hingezogen hat ------
        wh = min(WH, root.winfo_screenheight() - 110)
        if holder.get("placed"):
            x = root.winfo_x()
            y = root.winfo_y() + root.winfo_height() - wh
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x, y = sw - WW - 20, sh - wh - 80
            holder["placed"] = True
        root.geometry(f"{WW}x{wh}+{x}+{y}")
        root.update_idletasks()
        show_page(holder.get("page") if holder.get("page") in PAGES else "Aufnahme")

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
