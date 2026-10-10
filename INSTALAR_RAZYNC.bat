@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto failure
echo Dependencias instaladas. Execute INICIAR_RAZYNC.bat.
echo Para OCR, instale tambem Tesseract com o idioma Portugues.
pause
exit /b 0
:failure
echo A instalacao falhou. Confira se Python 3.12 esta instalado.
pause
exit /b 1
