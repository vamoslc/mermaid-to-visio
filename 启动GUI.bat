@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\MermaidToVisio.exe" (
  start "" "%~dp0dist\MermaidToVisio.exe"
) else (
  echo 未找到 exe，先用 Python 启动界面…
  python gui_app.py
)
