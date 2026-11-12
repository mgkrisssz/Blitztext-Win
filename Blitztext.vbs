' Startet Blitztext im Hintergrund OHNE Konsolenfenster (fuer den taeglichen Gebrauch)
Set sh = CreateObject("WScript.Shell")
appDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.CurrentDirectory = appDir
sh.Run """" & appDir & ".venv\Scripts\pythonw.exe"" """ & appDir & "blitztext.py""", 0, False
