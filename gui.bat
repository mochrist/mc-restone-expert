@echo off
rem Startet die GUI (rsx gui) und oeffnet den Browser. Optional: Datei als Argument, z. B.
rem   gui.bat scenarios\cmp-cmp3.yaml
cd /d "%~dp0"
where uv >nul 2>nul || (echo uv wurde nicht gefunden. Installation: https://docs.astral.sh/uv/ & pause & exit /b 1)
uv run rsx gui %*
if errorlevel 1 pause
