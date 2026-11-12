@echo off
REM ===== Blitztext-Win Einrichtung (einmalig ausfuehren) =====
cd /d "%~dp0"

echo.
echo Pruefe Python ...
py --version
if errorlevel 1 (
    echo.
    echo [FEHLER] Python wurde nicht gefunden.
    echo Bitte zuerst Python 3.10 oder neuer installieren: https://www.python.org/downloads/
    echo Beim Installieren "Add python.exe to PATH" anhaken!
    pause
    exit /b 1
)

echo.
echo Erstelle virtuelle Umgebung (.venv) ...
py -m venv .venv

echo.
echo Aktualisiere pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo Installiere Pakete - das laedt ~2 GB und dauert einige Minuten ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo ============================================================
echo  Fertig! Starte die App mit:  start_test.bat
echo  (Beim ersten Diktat laedt einmalig das Sprachmodell ~1,5 GB.)
echo ============================================================
pause
