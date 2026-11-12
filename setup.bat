@echo off
REM ===== Blitztext-Win Einrichtung (einmalig ausfuehren) / one-time setup =====
setlocal
cd /d "%~dp0"
title Blitztext-Win - Einrichtung

echo.
echo  ============================================================
echo    Blitztext-Win einrichten  /  Setting up Blitztext-Win
echo  ============================================================
echo.

REM --- 1) Python suchen ------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [FEHLER] Python wurde nicht gefunden.  /  Python was not found.
    echo.
    echo Bitte Python 3.10 oder neuer installieren / please install Python 3.10 or newer:
    echo   https://www.python.org/downloads/
    echo Beim Installieren "Add python.exe to PATH" anhaken!  /  Tick "Add python.exe to PATH"!
    echo.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2) Version pruefen (mindestens 3.10) ----------------------------------
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [FEHLER] Dein Python ist zu alt - benoetigt wird 3.10 oder neuer.
    echo          Your Python is too old - 3.10 or newer is required.
    %PY% --version
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
%PY% -c "import sys; sys.exit(1 if sys.version_info >= (3,14) else 0)"
if errorlevel 1 (
    echo [Hinweis] Sehr neues Python erkannt. Falls die Installation fehlschlaegt,
    echo           bitte Python 3.12 verwenden.  /  If installation fails, use Python 3.12.
    echo.
)
echo Python gefunden:
%PY% --version

REM --- 3) NVIDIA-Grafikkarte? ------------------------------------------------
set "REQ=requirements.txt"
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    set "REQ=requirements-gpu.txt"
    echo NVIDIA-Grafikkarte gefunden - GPU-Beschleunigung wird mitinstalliert.
    echo NVIDIA GPU found - installing GPU acceleration.
) else (
    echo Keine NVIDIA-Grafikkarte gefunden - Blitztext laeuft auf dem Prozessor.
    echo No NVIDIA GPU found - Blitztext will run on the CPU.
)

REM --- 4) Umgebung + Pakete --------------------------------------------------
echo.
echo Erstelle virtuelle Umgebung (.venv) ...
%PY% -m venv .venv
if errorlevel 1 (
    echo [FEHLER] Konnte die virtuelle Umgebung nicht anlegen.
    pause
    exit /b 1
)

echo.
echo Aktualisiere pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo Installiere Pakete - das dauert einige Minuten ...
echo Installing packages - this takes a few minutes ...
".venv\Scripts\python.exe" -m pip install -r %REQ%
if errorlevel 1 (
    echo.
    echo [FEHLER] Die Installation der Pakete ist fehlgeschlagen. Internet-Verbindung pruefen
    echo          und setup.bat nochmal ausfuehren.  /  Installation failed - check your
    echo          internet connection and run setup.bat again.
    pause
    exit /b 1
)

REM --- 5) Autostart anbieten --------------------------------------------------
echo.
choice /c JN /n /m "Soll Blitztext automatisch mit Windows starten? / Start with Windows? [J/N] "
if not errorlevel 2 (
    ".venv\Scripts\python.exe" autostart.py on
    echo Autostart eingerichtet.  /  Autostart enabled.
)

echo.
echo  ============================================================
echo    Fertig!  /  Done!
echo    Beim ersten Start laedt Blitztext einmalig das Sprachmodell
echo    (Fortschritt siehst du unten am Bildschirm) und oeffnet die
echo    Einstellungen.  /  On first start the speech model is
echo    downloaded once and the settings window opens.
echo  ============================================================
echo.
choice /c JN /n /m "Blitztext jetzt starten? / Start now? [J/N] "
if not errorlevel 2 (
    start "" wscript.exe "%~dp0Blitztext.vbs"
)
echo.
echo Spaeter starten mit  Blitztext.vbs  (unsichtbar) oder  start_test.bat  (mit Fenster).
pause
