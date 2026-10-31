@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 检查依赖...
python -c "import mermaid_render, PIL, PyInstaller" 2>nul
if errorlevel 1 (
  echo 安装依赖...
  pip install -r requirements.txt pyinstaller pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [2/3] 清理旧构建...
if exist build rd /s /q build
if exist dist\MermaidToVisio.exe del /f /q dist\MermaidToVisio.exe

echo [3/3] PyInstaller 打包（约 1~3 分钟）...
python -m PyInstaller --noconfirm --clean ^
  --name MermaidToVisio ^
  --windowed ^
  --onefile ^
  --collect-all mermaid_render ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import mermaid_to_visio ^
  gui_app.py

if errorlevel 1 (
  echo 打包失败
  exit /b 1
)

echo.
echo 完成: %cd%\dist\MermaidToVisio.exe
dir dist\MermaidToVisio.exe
pause
