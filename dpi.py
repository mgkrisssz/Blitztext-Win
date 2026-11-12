"""
Windows-Skalierung (125 %, 150 % ...): Ohne Hinweis vergroessert Windows die Fenster als Bild
und der Text wird unscharf. Mit "GDI-scaled" (Windows 10 ab 1809) zeichnet Windows die
GDI-Elemente - also auch den Text der Tk-Fenster - in der echten Aufloesung nach.
Die Fenstergroessen und das Layout bleiben dabei unveraendert (kein Umbau noetig).

Muss VOR dem ersten Fenster aufgerufen werden. Alle Fehler werden still ignoriert
(aeltere Windows-Versionen bleiben einfach wie bisher).
"""

import ctypes


def scharf_zeichnen():
    try:
        DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED))
    except Exception:
        pass
