"""
Blitztext-Win  -  Lokale Sprache-zu-Text-App fuer Windows
----------------------------------------------------------
- Global-Hotkey (Toggle): einmal druecken = Aufnahme starten, nochmal = stoppen
- Transkription lokal mit faster-whisper (large-v3) auf der GPU
- Text wird automatisch dort eingefuegt, wo der Cursor steht
- Tray-Icon in der Taskleiste mit Statusanzeige

Windows-Nachbau der Idee von blitztext-app (macOS, cmagnussen). Alles laeuft lokal.
"""

import io
import os
import re
import sys
import json
import site
import time
import queue
import ctypes
import threading

VERSION = "1.0.0"

# Protokoll zuerst starten, damit auch Fehler beim Import (und harte Abstuerze) ins Log kommen
import logsetup
logsetup.start(os.path.dirname(os.path.abspath(__file__)))

# Bei Windows-Skalierung >100 % Text scharf statt unscharf zeichnen (vor dem ersten Fenster!)
import dpi
dpi.scharf_zeichnen()

# ---------------------------------------------------------------------------
# 1) CUDA-DLLs (aus den nvidia-*-pip-Paketen) auffindbar machen  -- VOR Import!
# ---------------------------------------------------------------------------
def _register_cuda_dlls():
    dirs = []
    for base in site.getsitepackages() + [site.getusersitepackages()]:
        for sub in ("nvidia\\cublas\\bin", "nvidia\\cudnn\\bin", "nvidia\\cuda_nvrtc\\bin"):
            p = os.path.join(base, sub)
            if os.path.isdir(p):
                dirs.append(p)
    for p in dirs:
        try:
            os.add_dll_directory(p)
        except Exception:
            pass
        os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

_register_cuda_dlls()

import numpy as np
import sounddevice as sd
import pyperclip
from pynput import keyboard
from pynput.keyboard import Controller, Key
import pystray
from PIL import Image, ImageDraw

import autostart
import i18n
import updater
from i18n import t
from overlay import Overlay
from settings import open_settings, LANGS

# winsound ist nur unter Windows verfuegbar (kurze Feedback-Toene)
try:
    import winsound
except Exception:
    winsound = None

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# ---------------------------------------------------------------------------
# 2) Konfiguration
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "hotkey": "<f9>",                 # Toggle-Taste
    "model": "large-v3",              # Whisper-Modell
    "device": "cuda",                 # "cuda" oder "cpu"
    "compute_type": "float16",        # float16 (GPU) / int8 (CPU)
    "language": "de",                 # Diktiersprache ("" = Auto-Erkennung, "de", "hu", "en", ...)
    "translate_to_english": False,    # True = gesprochene Sprache ins Englische uebersetzen
    "samplerate": 16000,
    "input_device": None,             # Mikrofon-Name (aus dem Tray-Menue); None = System-Standard
    "beep": True,                     # kurze Toene bei Start/Stopp
    "paste": True,                    # True = automatisch einfuegen, False = nur Zwischenablage
    "auto_enter": False,              # True = nach dem Einfuegen automatisch Enter druecken (absenden)
    "type_instead_of_paste": False,   # True = Zeichen tippen statt Strg+V (fuer Apps ohne Einfuegen)
    "overlay": True,                  # kleines schwebendes Status-Fenster (HUD) anzeigen
    "initial_prompt": "",             # optionaler Kontext/Fachbegriffe fuer bessere Erkennung
    "push_to_talk": False,            # True = Hotkey gedrueckt halten = aufnehmen, loslassen = fertig
    "max_seconds": 300,               # Sicherheitslimit: Aufnahme stoppt automatisch (0 = aus)
    "dauerhaft_offen": True,          # Mikro offen halten (Anker braucht sonst ~3 s je Start)
    "voice_commands": True,           # gesprochenes "neue Zeile"/"neuer Absatz" -> Umbruch
    "hotkey_second": "<f8>",          # Zweit-Hotkey: diktiert einmalig in der Zweitsprache ("" = aus)
    "second_language": "en",          # Sprache des Zweit-Hotkeys (Kuerzel wie "en", "hu", "fr" ...)
    "theme": "mix",                   # Stil des Einstellungsfensters: "mix", "claude", "hell"
    "ui_language": "auto",            # Oberflaeche: "auto" (Windows-Sprache), "de", "en"
    "update_check": True,             # beim Start bei GitHub nach neuer Version fragen (nur Hinweis)
    "app_profiles": {                 # Fenstertitel-Schnipsel -> Einstellungs-Overrides
        "whatsapp": {"auto_enter": True},
        "word":     {"auto_enter": False}
    }
}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Warnung] config.json konnte nicht gespeichert werden: {e}")


def list_input_devices():
    """Eindeutige Mikrofon-Namen (nur MME-Geraete -> automatische Abtastraten-Umrechnung)."""
    names = []
    seen = set()
    try:
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and \
               sd.query_hostapis(d["hostapi"])["name"] == "MME":
                name = d["name"].strip()
                if "soundmapper" in name.lower() or "sound mapper" in name.lower():
                    continue  # generischer Standard-Eintrag -> haben wir als "Automatisch"
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
    except Exception as e:
        print(f"[Warnung] Geraeteliste: {e}")
    return names


def resolve_input_device(name):
    """Gespeicherten Mikrofon-Namen zur aktuellen Geraetenummer aufloesen.
    Gibt None zurueck (= System-Standard), wenn nichts gesetzt/gefunden."""
    if not name:
        return None
    fallback = None
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["name"].strip() == name:
                if sd.query_hostapis(d["hostapi"])["name"] == "MME":
                    return i
                if fallback is None:
                    fallback = i
    except Exception as e:
        print(f"[Warnung] Geraet aufloesen: {e}")
    return fallback


def _cuda_vorhanden():
    """True, wenn eine NVIDIA-Grafikkarte mit CUDA nutzbar ist."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                gelesen = json.load(f)
            # Altes Format (nur Ungarisch als Zweitsprache) uebernehmen
            if "hotkey_hu" in gelesen:
                gelesen.setdefault("hotkey_second", gelesen["hotkey_hu"])
                gelesen.setdefault("second_language", "hu")
                del gelesen["hotkey_hu"]
            cfg.update(gelesen)
        except Exception as e:
            print(f"[Warnung] config.json konnte nicht gelesen werden: {e}")
    else:
        # Erster Start: passendes Modell automatisch waehlen
        if _cuda_vorhanden():
            cfg.update(model="large-v3", device="cuda", compute_type="float16")
        else:
            cfg.update(model="small", device="cpu", compute_type="int8")
            print("[Blitztext] Keine NVIDIA-Grafikkarte gefunden -> Modell 'small' auf der CPU. "
                  "Im Einstellungsfenster kannst du ein anderes Modell waehlen.")
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return cfg

# ---------------------------------------------------------------------------
# 2b) Woerterbuch: Namen/Fachbegriffe fuer bessere Erkennung (initial_prompt)
# ---------------------------------------------------------------------------
VOCAB_PATH = os.path.join(APP_DIR, "woerterbuch.txt")

VOCAB_TEMPLATE = """# Blitztext-Woerterbuch
# Ein Begriff pro Zeile: Namen, Fachwoerter, Abkuerzungen, die Whisper
# sonst falsch schreibt. Zeilen mit '#' werden ignoriert.
# Nicht uebertreiben: ab ca. 50 Begriffen laesst der Effekt nach.
# Beispiele (Raute entfernen oder eigene Begriffe darunter schreiben):
Blitztext
# Max Mustermann
# Kubernetes
"""

def ensure_vocab_file():
    if not os.path.exists(VOCAB_PATH):
        try:
            with open(VOCAB_PATH, "w", encoding="utf-8") as f:
                f.write(VOCAB_TEMPLATE)
        except Exception as e:
            print(f"[Warnung] woerterbuch.txt anlegen: {e}")

def load_vocab():
    """Begriffe aus woerterbuch.txt einlesen (wird vor jeder Transkription gelesen,
    Aenderungen wirken also ohne Neustart)."""
    words = []
    try:
        with open(VOCAB_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    words.append(line)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[Warnung] woerterbuch.txt: {e}")
    return ", ".join(words)

# ---------------------------------------------------------------------------
# 2b2) App-Profile: aktives Fenster erkennen -> Einstellungen ueberschreiben
# ---------------------------------------------------------------------------
def active_window_title():
    try:
        h = ctypes.windll.user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(h, buf, 256)
        return buf.value
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# 2c) Sprachbefehle: gesprochene Kommandos -> Formatierung
# ---------------------------------------------------------------------------
# Reihenfolge wichtig: "neuer Absatz" vor "neue Zeile" ist hier egal, da
# getrennte Muster; Satzzeichen/Leerzeichen rund um den Befehl werden
# mitgeschluckt (Whisper setzt gern Kommas/Punkte davor und danach).
_VOICE_CMDS = [
    (r"neuer absatz|new paragraph|új bekezdés", "\n\n"),
    (r"neue zeile|new line|új sor", "\n"),
]

def apply_voice_commands(text):
    for pat, repl in _VOICE_CMDS:
        # Satzzeichen VOR dem Befehl bleiben (gehoeren zum Satz davor),
        # Satzzeichen direkt NACH dem Befehl werden mitgeschluckt
        text = re.sub(r"[ \t]*\b(?:%s)\b[.,;:!]?[ \t]*" % pat,
                      repl, text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    # nach Satzende gross weiterschreiben (nach Komma bewusst klein: Briefanrede)
    text = re.sub(r"([.!?])(\n+)(\S)",
                  lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
    return text.strip()

# ---------------------------------------------------------------------------
# 3) Tray-Icon-Grafiken je Status
# ---------------------------------------------------------------------------
def make_icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    return img

ICONS = {
    "loading":      make_icon((150, 150, 150, 255)),  # grau
    "idle":         make_icon((70, 130, 220, 255)),   # blau  = bereit
    "recording":    make_icon((220, 60, 60, 255)),    # rot   = nimmt auf
    "transcribing": make_icon((235, 170, 40, 255)),   # orange= verarbeitet
    "error":        make_icon((120, 40, 40, 255)),
}

# ---------------------------------------------------------------------------
# 3b) Modell-Download mit Fortschritt (sonst sieht man bei 1-3 GB nur ein graues Icon)
# ---------------------------------------------------------------------------
def modell_vorhanden(name):
    """True, wenn das Modell schon lokal liegt (kein Download noetig)."""
    try:
        from faster_whisper.utils import download_model
        download_model(name, local_files_only=True)
        return True
    except Exception:
        return False


def modell_herunterladen(name, fortschritt):
    """Laedt das Modell herunter und meldet den Fortschritt (0..1) an fortschritt().
    Wie faster_whisper.utils.download_model, aber mit eigener Fortschrittsanzeige."""
    from faster_whisper.utils import download_model, _MODELS
    import huggingface_hub
    from tqdm.auto import tqdm
    repo = name if "/" in name else _MODELS.get(name)
    if not repo:
        download_model(name)
        return

    class _Fortschritt(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["file"] = io.StringIO()        # keine Balken ins Protokoll schreiben
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            r = super().update(n)
            # nur der Balken der grossen Modell-Datei (Bytes), nicht der Datei-Zaehler
            if self.unit == "B" and self.total and self.total > 5_000_000:
                try:
                    fortschritt(min(0.99, self.n / self.total))
                except Exception:
                    pass
            return r

    huggingface_hub.snapshot_download(
        repo,
        allow_patterns=["config.json", "preprocessor_config.json", "model.bin",
                        "tokenizer.json", "vocabulary.*"],
        tqdm_class=_Fortschritt)


# ---------------------------------------------------------------------------
# 4) Kern-Logik
# ---------------------------------------------------------------------------
class Blitztext:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = None
        self.state = "loading"
        self.recording = False
        self.busy = False           # gerade Transkription/Einfuegen aktiv
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()   # Transkription und Modellwechsel (Spielmodus) schließen sich aus
        self._aktuell = cfg.get("model")     # welches Modell gerade geladen ist
        self._aktuell_ct = cfg.get("compute_type", "float16")
        self._spar_wunsch = False            # Spielmodus kam, bevor das Modell fertig geladen war
        self.spar = False                    # Spielmodus aktiv (sparsames Modell)
        self.frames = []            # aufgenommene Audio-Bloecke
        self.stream = None
        self.kbd = Controller()
        self.icon = None            # pystray Icon (spaeter gesetzt)
        self.overlay = Overlay(enabled=cfg.get("overlay", True))
        self.history = []           # letzte Transkripte (neuestes zuerst, max. 10)
        self._samples = 0           # aufgenommene Samples (fuer max_seconds)
        self._limit_hit = False
        self.lang_override = None   # per Zweit-Hotkey erzwungene Sprache (z. B. "en")
        self.erststart = False      # True beim allerersten Start (Willkommenshinweis nach dem Laden)
        self._lade_info = ""        # z. B. "Modell wird heruntergeladen ... 42 %" (Tooltip)

    # ---- akustisches Feedback ------------------------------------------
    def beep(self, kind):
        if not self.cfg.get("beep") or winsound is None:
            return
        def _play():
            try:
                if kind == "start":
                    winsound.Beep(880, 90)
                elif kind == "stop":
                    winsound.Beep(500, 90)
                elif kind == "error":
                    winsound.Beep(300, 250)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    # ---- Statusanzeige --------------------------------------------------
    def set_state(self, state, extra=""):
        self.state = state
        if self.icon is not None:
            titles = {
                "loading":      t("Blitztext - Modell wird geladen ...") + (("  " + self._lade_info) if self._lade_info else ""),
                "idle":         "%s  (%s: %s)%s" % (t("Blitztext - bereit"), t("Hotkey"), self.cfg["hotkey"], "  [Spielmodus: sparsames Modell]" if self.spar else ""),
                "recording":    t("Blitztext - HOERE ZU ... (Hotkey = fertig, Esc = verwerfen)"),
                "transcribing": t("Blitztext - verarbeite ..."),
                "error":        t("Blitztext - Fehler") + ": " + extra,
            }
            self.icon.icon = ICONS.get(state, ICONS["idle"])
            self.icon.title = titles.get(state, "Blitztext")

    # ---- Modell laden (im Hintergrund) ---------------------------------
    def load_model(self):
        from faster_whisper import WhisperModel

        def _try(device, compute_type):
            if not modell_vorhanden(self.cfg["model"]):
                print(f"[Blitztext] Modell {self.cfg['model']} wird heruntergeladen ...")
                self.overlay.status(t("Modell wird heruntergeladen") + " …")
                modell_herunterladen(self.cfg["model"], self._modell_fortschritt)
                self._lade_info = ""
                self.overlay.hide()
            print(f"[Blitztext] Lade {self.cfg['model']} auf {device} ({compute_type}) ...")
            self.model = WhisperModel(self.cfg["model"], device=device,
                                      compute_type=compute_type)
            self._aktuell, self._aktuell_ct = self.cfg["model"], compute_type
            warm = np.zeros(self.cfg["samplerate"], dtype=np.float32)
            list(self.model.transcribe(warm, language=self.cfg.get("language") or None)[0])

        try:
            _try(self.cfg["device"], self.cfg["compute_type"])
            self.set_state("idle")
            print("[Blitztext] Modell bereit.")
            self._bereit_hinweis()
            if self._spar_wunsch:
                self.set_sparmodus(True)
        except Exception as e:
            # Modell fehlt und liess sich nicht laden (meist: kein Internet) -> kein CPU-Rueckfall
            if not modell_vorhanden(self.cfg["model"]):
                print(f"[Fehler] Modell {self.cfg['model']} nicht verfuegbar: {e}")
                self._lade_info = ""
                self.overlay.status(t("Modell konnte nicht geladen werden – Internet?"))
                threading.Timer(7, self.overlay.hide).start()
                self.set_state("error", t("Modell konnte nicht geladen werden – Internet?"))
                return
            # Automatischer Rueckfall auf CPU (z. B. PC ohne NVIDIA-GPU)
            if self.cfg["device"] != "cpu":
                print(f"[Warnung] GPU nicht nutzbar ({e}). Wechsle auf CPU (langsamer) ...")
                try:
                    _try("cpu", "int8")
                    self.set_state("idle")
                    self._bereit_hinweis()
                    print("[Blitztext] Modell bereit (CPU). Tipp: fuer Tempo 'model' "
                          "in config.json auf 'small' oder 'medium' stellen.")
                    return
                except Exception as e2:
                    e = e2
            print(f"[Fehler] Modell konnte nicht geladen werden: {e}")
            self.set_state("error", str(e))

    def _modell_fortschritt(self, frac):
        """Wird waehrend des Downloads aufgerufen (Hintergrund-Thread)."""
        pct = int(frac * 100)
        if self._lade_info == "%d %%" % pct:
            return                                   # nur bei Aenderung aktualisieren
        text = "%s … %d %%" % (t("Modell wird heruntergeladen"), pct)
        self._lade_info = "%d %%" % pct
        self.overlay.status(text)
        self.set_state("loading")

    def _bereit_hinweis(self):
        """Nach dem allerersten Laden kurz sagen, wie es geht."""
        if self.erststart:
            self.erststart = False
            key = (self.cfg["hotkey"] or "").replace("<", "").replace(">", "").upper()
            self.overlay.result(t("Bereit – drücke {key} zum Diktieren").format(key=key))

    def reload_model(self):
        """Gewaehltes Modell (cfg["model"]) neu laden, z. B. nach Wechsel im Einstellungsfenster.
        Wartet, bis eine laufende Transkription fertig ist; laeuft im Hintergrund."""
        def _arbeit():
            import gc
            with self.model_lock:
                alt, self.model = self.model, None
                try:
                    if alt is not None:
                        alt.model.unload_model()
                except Exception:
                    pass
                del alt
                gc.collect()
                self.set_state("loading")
                # CPU-Modus braucht int8, GPU float16 (sonst Fehler beim Laden)
                if self.cfg.get("device") == "cpu":
                    self.cfg["compute_type"] = "int8"
                self.spar = False
                self.load_model()
        threading.Thread(target=_arbeit, daemon=True).start()

    # ---- Spielmodus: sparsames Modell, solange ein Spiel läuft -----------
    def set_sparmodus(self, an):
        """Tauscht large-v3 gegen ein kleineres Modell (spar_model, Standard medium/int8_float16), damit das Spiel
        mehr Grafikspeicher hat, und danach zurück. Wartet, bis eine laufende Transkription fertig ist."""
        self._spar_wunsch = bool(an)
        if self.model is None or self.cfg.get("device") == "cpu":
            return                            # noch nicht geladen (load_model holt es nach) oder CPU (spart keinen Grafikspeicher)
        from faster_whisper import WhisperModel
        import gc
        ziel = self.cfg.get("spar_model", "medium") if an else self.cfg["model"]
        ct = self.cfg.get("spar_compute_type", "int8_float16") if an else self.cfg["compute_type"]
        if ziel == self._aktuell:
            self.spar = bool(an)
            return
        with self.model_lock:
            vorher, vorher_ct = self._aktuell, self._aktuell_ct
            warm = np.zeros(self.cfg["samplerate"], dtype=np.float32)
            try:
                alt = self.model
                self.model = None
                try:
                    alt.model.unload_model()      # ERST entladen: nur so gibt die Grafikkarte den Speicher wirklich zurück
                except Exception:
                    pass
                del alt
                gc.collect()
                print(f"[Blitztext] Spielmodus {'AN' if an else 'AUS'}: wechsle auf {ziel} ({ct}) ...")
                neu = WhisperModel(ziel, device=self.cfg["device"], compute_type=ct)
                list(neu.transcribe(warm, language=self.cfg.get("language") or None)[0])
                self.model, self._aktuell, self._aktuell_ct = neu, ziel, ct
            except Exception as e:
                print(f"[Blitztext] Wechsel auf {ziel} fehlgeschlagen ({e}), lade {vorher} wieder.")
                try:
                    self.model = WhisperModel(vorher, device=self.cfg["device"], compute_type=vorher_ct)
                    self._aktuell, self._aktuell_ct = vorher, vorher_ct
                except Exception as e2:
                    print(f"[Blitztext] Altes Modell nicht ladbar: {e2}")
        gc.collect()
        self.spar = bool(an)
        if self.state == "idle":
            self.set_state("idle")            # Symbol-Titel auffrischen
        print(f"[Blitztext] Modell jetzt: {ziel}")

    # ---- Audio-Aufnahme -------------------------------------------------
    def _audio_cb(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio] {status}")
        if not self.recording:
            return  # Mikro bleibt offen, Daten werden nur waehrend der Aufnahme gesammelt
        self.frames.append(indata.copy())
        # Sicherheitslimit: bei Ueberschreiten automatisch stoppen
        self._samples += frames
        maxs = self.cfg.get("max_seconds") or 0
        if maxs and not self._limit_hit and self._samples >= maxs * self.cfg["samplerate"]:
            self._limit_hit = True
            print(f"[Blitztext] Limit von {maxs}s erreicht -> Aufnahme wird gestoppt.")
            # nicht im Audio-Callback stoppen (Deadlock), sondern im eigenen Thread
            threading.Thread(target=self.toggle, daemon=True).start()
        # Live-Pegel fuer das HUD (RMS -> 0..1)
        try:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            self.overlay.set_level(min(1.0, rms * 18.0))
            if len(self.frames) == 1:
                print(f"[debug] erster Audio-Block: shape={indata.shape} rms={rms:.5f}")
        except Exception as e:
            print(f"[debug] audio_cb Fehler: {e}")

    def open_stream(self):
        """Mikro oeffnen (und offen halten): manche Geraete (Anker PowerConf)
        brauchen zum Oeffnen ~3 s, das soll nicht bei jedem Tastendruck passieren."""
        if self.stream is not None and self.stream.active:
            return
        self.close_stream()
        dev = resolve_input_device(self.cfg.get("input_device"))
        if self.cfg.get("input_device") and dev is None:
            print(f"[Warnung] Mikrofon '{self.cfg['input_device']}' nicht gefunden "
                  f"-> System-Standard.")
        self.stream = sd.InputStream(
            device=dev,
            samplerate=self.cfg["samplerate"],
            channels=1,
            dtype="float32",
            callback=self._audio_cb,
        )
        self.stream.start()
        try:
            used = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
        except Exception:
            used = "Standard"
        print(f"[Blitztext] Mikro offen ({used}).")

    def close_stream(self):
        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        finally:
            self.stream = None

    def start_recording(self, lang=None):
        self.frames = []
        self._samples = 0
        self._limit_hit = False
        self.lang_override = lang
        if lang:
            print(f"[Blitztext] Diese Aufnahme in Sprache: {lang}")
        self.open_stream()
        self.recording = True
        self.set_state("recording")
        self.overlay.recording()
        self.beep("start")
        print("[Blitztext] Aufnahme gestartet.")

    def stop_recording_and_process(self):
        self.recording = False
        if not self.cfg.get("dauerhaft_offen", True):
            self.close_stream()
        self.beep("stop")
        self.set_state("transcribing")
        self.overlay.processing()
        print("[Blitztext] Aufnahme gestoppt, transkribiere ...")

        if not self.frames:
            self.overlay.hide()
            self.set_state("idle")
            return
        n_frames = len(self.frames)
        audio = np.concatenate(self.frames, axis=0).flatten().astype(np.float32)
        self.frames = []
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        print(f"[debug] Bloecke={n_frames}  Samples={audio.size}  Dauer={audio.size/self.cfg['samplerate']:.2f}s  Peak={peak:.4f}")

        # zu leise / zu kurz? -> nichts tun
        if audio.shape[0] < self.cfg["samplerate"] * 0.3:
            print("[Blitztext] Aufnahme zu kurz, ignoriert.")
            self.overlay.hide()
            self.set_state("idle")
            return

        try:
            t0 = time.time()
            task = "translate" if self.cfg.get("translate_to_english") else "transcribe"
            # Woerterbuch + optionaler config-Prompt als Erkennungshilfe
            prompt = ", ".join(p for p in (self.cfg.get("initial_prompt") or "",
                                           load_vocab()) if p) or None
            with self.model_lock:
                segments, info = self.model.transcribe(
                    audio,
                    language=self.lang_override or self.cfg.get("language") or None,
                    task=task,
                    vad_filter=True,
                    initial_prompt=prompt,
                )
                text = "".join(s.text for s in segments).strip()
            if text and self.cfg.get("voice_commands", True):
                text = apply_voice_commands(text)
            dt = time.time() - t0
            dur = audio.shape[0] / self.cfg["samplerate"]
            print(f"[Blitztext] {dur:.1f}s Audio in {dt:.2f}s transkribiert: {text!r}")
        except Exception as e:
            print(f"[Fehler] Transkription: {e}")
            self.beep("error")
            self.overlay.hide()
            self.set_state("error", str(e))
            time.sleep(2)
            self.set_state("idle")
            return

        if text:
            self.history.insert(0, text)
            del self.history[10:]
            if self.icon is not None:
                try:
                    self.icon.update_menu()
                except Exception:
                    pass
            self.output_text(text)
            self.overlay.result(text)
        else:
            self.overlay.hide()
        self.set_state("idle")

    # ---- Text ausgeben --------------------------------------------------
    def _profile_overrides(self):
        """App-Profil fuers aktive Fenster suchen (Titel-Schnipsel aus config)."""
        title = active_window_title().lower()
        for frag, over in (self.cfg.get("app_profiles") or {}).items():
            if frag.lower() in title:
                return frag, over
        return None, {}

    def output_text(self, text):
        frag, over = self._profile_overrides()
        if frag:
            print(f"[Blitztext] App-Profil '{frag}' aktiv: {over}")
        def opt(key, default=None):
            return over.get(key, self.cfg.get(key, default))

        print(f"[debug] output_text: fuege ein (paste={opt('paste', True)}, "
              f"type={opt('type_instead_of_paste')}): {text!r}")
        if not opt("paste", True):
            pyperclip.copy(text)
            print("[Blitztext] Text in Zwischenablage kopiert.")
            return

        if opt("type_instead_of_paste"):
            # Zeichen direkt tippen (fuer Apps, die Strg+V nicht m/anders behandeln)
            time.sleep(0.05)
            self.kbd.type(text)
        else:
            # Standard: ueber Zwischenablage + Strg+V einfuegen
            pyperclip.copy(text)
            time.sleep(0.08)
            self.kbd.press(Key.ctrl)
            self.kbd.press('v')
            self.kbd.release('v')
            self.kbd.release(Key.ctrl)

        # Optional: automatisch Enter druecken (absenden)
        if opt("auto_enter"):
            time.sleep(0.06)
            self.kbd.press(Key.enter)
            self.kbd.release(Key.enter)
            print("[Blitztext] Auto-Enter gedrueckt.")

    # ---- Hotkey-Steuerung ----------------------------------------------
    def _stop_async(self):
        """Aufnahme beenden, Transkription im Worker-Thread (Aufrufer haelt lock)."""
        self.busy = True
        def _work():
            try:
                self.stop_recording_and_process()
            finally:
                self.busy = False
        threading.Thread(target=_work, daemon=True).start()

    def toggle(self, lang=None):
        # Schnell reagieren; lange Arbeit in Worker-Thread auslagern
        with self.lock:
            if self.state == "loading":
                print("[Blitztext] Modell laedt noch, bitte warten ...")
                self.beep("error")
                return
            if self.busy:
                print("[Blitztext] Verarbeite noch, bitte warten ...")
                return
            if not self.recording:
                self.start_recording(lang)
            else:
                self._stop_async()

    def ptt_press(self, lang=None):
        """Push-to-Talk: Hotkey gedrueckt -> Aufnahme starten."""
        with self.lock:
            if self.state == "loading" or self.busy:
                self.beep("error")
                return
            if not self.recording:
                self.start_recording(lang)

    def ptt_release(self):
        """Push-to-Talk: Hotkey losgelassen -> Aufnahme beenden."""
        with self.lock:
            if self.recording and not self.busy:
                self._stop_async()

    def cancel_recording(self):
        """Esc waehrend der Aufnahme: verwerfen, nichts transkribieren."""
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            if not self.cfg.get("dauerhaft_offen", True):
                self.close_stream()
            self.frames = []
            self.beep("error")
            self.overlay.hide()
            self.set_state("idle")
            print("[Blitztext] Aufnahme verworfen (Esc).")

# ---------------------------------------------------------------------------
# 5) Zusammenbau: Hotkey-Listener + Tray
# ---------------------------------------------------------------------------
def main():
    erststart = not os.path.exists(CONFIG_PATH)
    cfg = load_config()
    i18n.set_language(cfg.get("ui_language", "auto"))
    ensure_vocab_file()
    print("=" * 60)
    print(" Blitztext-Win  -  lokale Diktier-App")
    print(f" Hotkey (Toggle): {cfg['hotkey']}"
          + (f"  |  Zweitsprache ({cfg.get('second_language')}): {cfg['hotkey_second']}" if cfg.get("hotkey_second") else ""))
    print(f" Modell: {cfg['model']}  |  Geraet: {cfg['device']} ({cfg['compute_type']})")
    print(f" Sprache: {cfg['language'] or 'auto'}")
    print("=" * 60)

    app = Blitztext(cfg)
    app.erststart = erststart

    # Modell im Hintergrund laden, damit das Tray-Icon sofort erscheint
    threading.Thread(target=app.load_model, daemon=True).start()
    # Optionaler Spielmodus: nur aktiv, wenn in config.json "spielmodus_pfad" auf einen Ordner
    # mit einem Modul spielmodus.py zeigt (beobachten(callback)). Standard: aus.
    if cfg.get("spielmodus_pfad"):
        try:
            sys.path.insert(0, cfg["spielmodus_pfad"])
            import spielmodus
            spielmodus.beobachten(app.set_sparmodus)
        except Exception as e:
            print(f"[Spielmodus] nicht aktiv: {e}")

    # Mikro gleich beim Start oeffnen und offen halten (kein 3-s-Warten pro Tastendruck)
    def _mic_warm():
        try:
            if cfg.get("dauerhaft_offen", True):
                app.open_stream()
        except Exception as e:
            print(f"[Warnung] Mikro vorab oeffnen fehlgeschlagen: {e}")
    threading.Thread(target=_mic_warm, daemon=True).start()

    # Global-Hotkeys: Haupt-Hotkey + optionaler Zweit-Hotkey (erzwingt die Zweitsprache),
    # Toggle-Modus ODER Push-to-Talk (halten), plus Esc = verwerfen.
    # Eigener Listener statt GlobalHotKeys, weil wir auch das Loslassen brauchen.
    hk_state = {"hotmap": [], "allkeys": set(), "suspended": False}

    def rebuild_hotkeys():
        hm = [(set(keyboard.HotKey.parse(cfg["hotkey"])), None)]
        if cfg.get("hotkey_second"):
            try:
                hm.append((set(keyboard.HotKey.parse(cfg["hotkey_second"])),
                           cfg.get("second_language") or "en"))
            except Exception as e:
                print(f"[Warnung] hotkey_second ungueltig: {e}")
        hk_state["hotmap"] = hm
        hk_state["allkeys"] = set().union(*(c for c, _ in hm))

    rebuild_hotkeys()
    pressed = set()

    def on_press(key):
        if hk_state["suspended"]:      # Einstellungsfenster nimmt gerade Taste auf
            return
        if key == keyboard.Key.esc and app.recording:
            app.cancel_recording()
            return
        k = listener.canonical(key)
        if k in hk_state["allkeys"] and k not in pressed:  # Tasten-Autorepeat ignorieren
            pressed.add(k)
            for combo, lang in hk_state["hotmap"]:
                if k in combo and combo <= pressed:
                    if cfg.get("push_to_talk"):
                        app.ptt_press(lang)
                    else:
                        app.toggle(lang)
                    break

    def on_release(key):
        k = listener.canonical(key)
        if k in pressed:
            pressed.discard(k)
            if cfg.get("push_to_talk") and not hk_state["suspended"]:
                app.ptt_release()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # Tray-Menue
    def on_quit(icon, item):
        try:
            if app.stream is not None:
                app.stream.stop(); app.stream.close()
        except Exception:
            pass
        app.overlay.stop()
        listener.stop()
        icon.stop()

    def toggle_paste(icon, item):
        cfg["paste"] = not cfg.get("paste", True)
        save_config(cfg)

    def toggle_enter(icon, item):
        cfg["auto_enter"] = not cfg.get("auto_enter", False)
        save_config(cfg)
        print(f"[Blitztext] Auto-Enter: {'AN' if cfg['auto_enter'] else 'AUS'}")

    def set_lang(code):
        cfg["language"] = code
        save_config(cfg)
        print(f"[Blitztext] Sprache: {code or 'Automatisch'}")

    def toggle_translate(icon, item):
        cfg["translate_to_english"] = not cfg.get("translate_to_english", False)
        save_config(cfg)
        print(f"[Blitztext] Ins Englische uebersetzen: "
              f"{'AN' if cfg['translate_to_english'] else 'AUS'}")

    def lang_submenu():
        items = []
        for label, code in LANGS:
            items.append(pystray.MenuItem(
                (lambda l: (lambda item: t(l)))(label),
                (lambda c: (lambda icon, item: set_lang(c)))(code),
                checked=(lambda c: (lambda item: (cfg.get("language") or "") == c))(code),
                radio=True,
            ))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem(
            lambda item: t("Ins Englische übersetzen"),
            toggle_translate,
            checked=lambda item: cfg.get("translate_to_english", False),
        ))
        return pystray.Menu(*items)

    def set_mic(name):
        cfg["input_device"] = name
        save_config(cfg)
        if app.stream is not None:
            app.close_stream()  # naechstes Oeffnen nimmt das neue Geraet
        print(f"[Blitztext] Mikrofon gewaehlt: {name or 'System-Standard'}")

    def mic_submenu():
        items = [pystray.MenuItem(
            lambda item: t("Automatisch (System-Standard)"),
            lambda icon, item: set_mic(None),
            checked=lambda item: not cfg.get("input_device"),
            radio=True,
        )]
        for name in list_input_devices():
            items.append(pystray.MenuItem(
                name,
                (lambda n: (lambda icon, item: set_mic(n)))(name),
                checked=(lambda n: (lambda item: cfg.get("input_device") == n))(name),
                radio=True,
            ))
        return pystray.Menu(*items)

    def toggle_ptt(icon, item):
        cfg["push_to_talk"] = not cfg.get("push_to_talk", False)
        save_config(cfg)
        print(f"[Blitztext] Push-to-Talk: {'AN (halten)' if cfg['push_to_talk'] else 'AUS (Toggle)'}")

    # -- Autostart: Logik liegt in autostart.py (auch von setup.bat genutzt) --
    def toggle_autostart(icon, item):
        autostart.set_enabled(not autostart.enabled())

    def open_vocab(icon, item):
        ensure_vocab_file()
        try:
            os.startfile(VOCAB_PATH)
        except Exception as e:
            print(f"[Warnung] Woerterbuch oeffnen: {e}")

    def set_hotkey(which, value):
        """which: 'hotkey' oder 'hotkey_second'; value '' = aus (nur second).
        Rueckgabe: Fehlertext oder None; wirkt sofort, ohne Neustart."""
        if value:
            try:
                keyboard.HotKey.parse(value)
            except Exception as e:
                return str(e)
        elif which == "hotkey":
            return "Haupt-Hotkey darf nicht leer sein"
        cfg[which] = value
        save_config(cfg)
        rebuild_hotkeys()
        print(f"[Blitztext] {which} = {value or 'aus'}")
        return None

    def open_settings_window(icon=None, item=None):
        open_settings({
            "cfg": cfg,
            "save": lambda: save_config(cfg),
            "devices": list_input_devices,
            "autostart_get": autostart.enabled,
            "autostart_set": autostart.set_enabled,
            "refresh_tray": lambda: refresh_menu(icon, None),
            "open_vocab": lambda: open_vocab(None, None),
            "set_hotkey": set_hotkey,
            "reload_model": app.reload_model,
            "suspend": lambda b: hk_state.__setitem__("suspended", bool(b)),
            "resolve_device": resolve_input_device,
        })

    def history_submenu():
        # dynamisch: wird bei jedem Oeffnen des Menues neu erzeugt
        def items():
            if not app.history:
                yield pystray.MenuItem(lambda item: t("(noch nichts diktiert)"), None, enabled=False)
            for eintrag in list(app.history):
                label = eintrag if len(eintrag) <= 50 else eintrag[:50] + "..."
                yield pystray.MenuItem(
                    label,
                    (lambda s: (lambda icon, item: pyperclip.copy(s)))(eintrag),
                )
        return pystray.Menu(items)

    def refresh_menu(icon, item):
        icon.menu = build_menu()
        icon.update_menu()

    upd = {"tag": None, "url": None}

    def open_update(icon, item):
        if upd["url"]:
            import webbrowser
            webbrowser.open(upd["url"])

    def open_log(icon, item):
        try:
            os.startfile(logsetup.log_pfad(APP_DIR))
        except Exception as e:
            print(f"[Warnung] Protokoll oeffnen: {e}")

    def build_menu():
        return pystray.Menu(
            pystray.MenuItem(lambda item: "⬆ %s: %s" % (t("Update verfügbar"), upd["tag"]),
                             open_update, visible=lambda item: bool(upd["tag"])),
            # default=True -> Doppelklick auf das Tray-Icon oeffnet die Einstellungen
            pystray.MenuItem(lambda item: t("Einstellungen ..."), open_settings_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"{t('Status')}: {app.state}", None, enabled=False),
            pystray.MenuItem(lambda item: f"{t('Hotkey')}: {cfg['hotkey']}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: t("Mikrofon"), mic_submenu()),
            pystray.MenuItem(lambda item: t("Sprache"), lang_submenu()),
            pystray.MenuItem(lambda item: t("Verlauf (klick = kopieren)"), history_submenu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: t("Gedrückt halten (Push-to-Talk)"),
                toggle_ptt,
                checked=lambda item: cfg.get("push_to_talk", False),
            ),
            pystray.MenuItem(
                lambda item: t("Automatisch einfügen"),
                toggle_paste,
                checked=lambda item: cfg.get("paste", True),
            ),
            pystray.MenuItem(
                lambda item: t("Automatisch Enter (absenden)"),
                toggle_enter,
                checked=lambda item: cfg.get("auto_enter", False),
            ),
            pystray.MenuItem(
                lambda item: t("Mit Windows starten"),
                toggle_autostart,
                checked=lambda item: autostart.enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: t("Wörterbuch bearbeiten"), open_vocab),
            pystray.MenuItem(lambda item: t("Mikrofonliste aktualisieren"), refresh_menu),
            pystray.MenuItem(lambda item: t("Protokoll öffnen"), open_log),
            pystray.MenuItem(lambda item: t("Beenden"), on_quit),
        )

    icon = pystray.Icon("blitztext", ICONS["loading"], "Blitztext - Modell wird geladen ...")
    icon.menu = build_menu()
    app.icon = icon

    def _neue_version(tag, url):
        upd.update(tag=tag, url=url)
        try:
            icon.update_menu()
            icon.notify(t("Neue Version {tag} verfügbar").format(tag=tag), "Blitztext")
        except Exception:
            pass

    if cfg.get("update_check", True):
        updater.pruefen(VERSION, _neue_version)

    def _nach_start(ic):
        ic.visible = True                       # eigenes setup ersetzt das Standard-Setup
        if erststart:                           # allererster Start: Einstellungen zeigen
            time.sleep(1.5)
            open_settings_window()

    icon.run(setup=_nach_start)

if __name__ == "__main__":
    main()
