"""
Schwebendes Status-HUD fuer Blitztext (kleines Pill-Fenster).

- randlos, immer im Vordergrund, abgerundet (via -transparentcolor)
- WICHTIG: das Fenster ist "disabled" -> es kann keinen Fokus stehlen,
  damit das Auto-Einfuegen (Strg+V) im richtigen Programm landet.
- Laeuft in einem eigenen Thread mit eigener Tk-mainloop.
  Kommunikation nur ueber thread-sichere Methoden.
"""

import math
import queue
import threading

# Fenster-/Stil-Konstanten
W, H = 340, 84
MARGIN = 8
CHROMA = "#ff00ff"          # wird komplett transparent geschaltet
PILL = "#202227"
TEXT = "#f2f2f4"
SUBTLE = "#9aa0a8"
COL_REC = "#e6413c"         # rot  = Aufnahme
COL_PROC = "#ecaa28"        # orange = Verarbeitung
COL_DONE = "#3bbf6b"        # gruen = fertig
N_BARS = 30


class Overlay:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self._level = 0.0            # 0..1, von aussen gesetzt (Audio-Thread)
        self._q = queue.Queue()
        self._ready = threading.Event()
        self._ok = False
        if not enabled:
            self._ready.set()
            return
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        self._ready.wait(5)

    # ---- oeffentliche, thread-sichere API ------------------------------
    def set_level(self, v):
        self._level = 0.0 if v < 0 else (1.0 if v > 1 else v)

    def recording(self):   self._put(("recording", None))
    def processing(self):  self._put(("processing", None))
    def result(self, txt): self._put(("result", txt))
    def hide(self):        self._put(("hide", None))
    def stop(self):        self._put(("quit", None))

    def _put(self, item):
        if self._ok:
            self._q.put(item)

    # ---- alles ab hier laeuft im Tk-Thread -----------------------------
    def _run(self):
        try:
            import tkinter as tk
        except Exception as e:
            print(f"[Overlay] tkinter nicht verfuegbar, HUD deaktiviert: {e}")
            self._ready.set()
            return

        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", CHROMA)  # runde Ecken/Transparenz (Windows)
        except Exception:
            pass
        try:
            self.root.attributes("-disabled", True)            # kein Fokusklau (Windows)
        except Exception:
            pass
        self.root.configure(bg=CHROMA)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - W) // 2
        y = sh - H - 90
        self.root.geometry(f"{W}x{H}+{x}+{y}")

        self.c = tk.Canvas(self.root, width=W, height=H, bg=CHROMA,
                           highlightthickness=0, bd=0)
        self.c.pack()

        # Pill-Hintergrund (abgerundet)
        self._round_rect(MARGIN, MARGIN, W - MARGIN, H - MARGIN, 18, fill=PILL, outline="")

        # Status-Punkt
        self.dot_cx, self.dot_cy, self.dot_r = 30, 30, 8
        self.dot = self.c.create_oval(
            self.dot_cx - self.dot_r, self.dot_cy - self.dot_r,
            self.dot_cx + self.dot_r, self.dot_cy + self.dot_r,
            fill=COL_REC, outline="")

        # Statustext
        self.label = self.c.create_text(50, 30, anchor="w", text="",
                                        fill=TEXT, font=("Segoe UI", 12, "bold"))

        # Equalizer-Balken
        self.bars = []
        bx0, bx1 = 24, W - 24
        bw = (bx1 - bx0) / N_BARS
        self.base_y = H - 22
        for i in range(N_BARS):
            x0 = bx0 + i * bw + 1
            r = self.c.create_rectangle(x0, self.base_y - 2, x0 + bw - 2, self.base_y,
                                        fill=COL_REC, outline="")
            self.bars.append(r)

        self.mode = "idle"          # idle / rec / proc / done
        self._phase = 0.0
        self._disp = [0.0] * N_BARS  # geglaettete Balkenhoehen

        self._ok = True
        self._ready.set()
        self.root.after(20, self._poll)
        self.root.after(33, self._animate)
        self.root.mainloop()

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.c.create_polygon(pts, smooth=True, **kw)

    def _poll(self):
        try:
            while True:
                cmd, arg = self._q.get_nowait()
                self._handle(cmd, arg)
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _handle(self, cmd, arg):
        if cmd == "recording":
            self.mode = "rec"
            self.c.itemconfig(self.label, text="Höre zu …", fill=TEXT)
            self.c.itemconfig(self.dot, fill=COL_REC)
            self._set_bar_color(COL_REC)
            self.root.deiconify()
        elif cmd == "processing":
            self.mode = "proc"
            self.c.itemconfig(self.label, text="Verarbeite …", fill=TEXT)
            self.c.itemconfig(self.dot, fill=COL_PROC)
            self._set_bar_color(COL_PROC)
            self.root.deiconify()
        elif cmd == "result":
            self.mode = "done"
            txt = (arg or "").strip().replace("\n", " ")
            if len(txt) > 46:
                txt = txt[:45] + "…"
            self.c.itemconfig(self.label, text=txt or "(nichts erkannt)", fill=TEXT)
            self.c.itemconfig(self.dot, fill=COL_DONE)
            self._set_bar_color(COL_DONE)
            self.root.deiconify()
            self.root.after(1700, self._auto_hide)
        elif cmd == "hide":
            self.mode = "idle"
            self.root.withdraw()
        elif cmd == "quit":
            try:
                self.root.destroy()
            except Exception:
                pass

    def _auto_hide(self):
        if self.mode == "done":
            self.mode = "idle"
            self.root.withdraw()

    def _set_bar_color(self, color):
        for r in self.bars:
            self.c.itemconfig(r, fill=color)

    def _animate(self):
        try:
            if self.root.state() != "withdrawn":
                self._phase += 0.35
                lvl = self._level
                for i, r in enumerate(self.bars):
                    if self.mode == "rec":
                        # Pegel-gesteuerte, lebendige Balken
                        env = 0.35 + 0.65 * math.sin(self._phase + i * 0.5) ** 2
                        target = lvl * env
                    elif self.mode == "proc":
                        # wandernde Welle waehrend der Verarbeitung
                        target = 0.25 + 0.6 * max(0.0, math.sin(self._phase * 1.3 - i * 0.4))
                    else:  # done -> ruhig auslaufen
                        target = 0.12
                    # glaetten
                    self._disp[i] += (target - self._disp[i]) * 0.4
                    h = 3 + self._disp[i] * (H - 54)
                    x0, _, x1, _ = self.c.coords(r)
                    self.c.coords(r, x0, self.base_y - h, x1, self.base_y)

                # Punkt pulsieren lassen
                if self.mode in ("rec", "proc"):
                    pr = self.dot_r + 2.2 * (0.5 + 0.5 * math.sin(self._phase * 1.5))
                    self.c.coords(self.dot,
                                  self.dot_cx - pr, self.dot_cy - pr,
                                  self.dot_cx + pr, self.dot_cy + pr)
        except Exception:
            pass
        self.root.after(33, self._animate)
