@echo off
setlocal
cd /d "%~dp0"
if not exist ".env\Scripts\pythonw.exe" (
    echo L'application n'est pas encore installee sur cet ordinateur.
    echo Demandez de l'aide a la personne qui vous a fourni Mouvement.
    pause
    exit /b 1
)
start "" ".env\Scripts\pythonw.exe" "app_live_cv.py"
