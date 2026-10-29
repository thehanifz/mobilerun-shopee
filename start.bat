@echo off
setlocal
title Shopee Video Uploader Agent
cd /d "%~dp0"

echo ============================================
echo  Shopee Video Uploader Agent - 1 perintah
echo ============================================
echo.

:: --- 0. Cek .env ---
if not exist ".env" (
  echo  [!] File .env belum ada.
  echo  Salin "config.example.env" menjadi ".env" lalu isi dulu,
  echo  kemudian jalankan start.bat lagi.
  echo.
  pause
  exit /b 1
)

:: --- PATH: uv, platform-tools, mobilerun ---
set "PATH=%USERPROFILE%\.local\bin;%~dp0platform-tools;%PATH%"

:: --- 1. Setup pertama (sekali saja): install + pairing HP + Portal APK ---
if not exist ".installed" (
  echo  [*] Setup pertama kali...
  echo      Pastikan HP dan PC satu WiFi, Wireless debugging sudah nyala,
  echo      dan aplikasi Shopee sudah login di HP.
  echo.
  powershell -ExecutionPolicy ByPass -File "setup_pc.ps1"
  if errorlevel 1 (
    echo.
    echo  [!] Setup gagal. Periksa pesan di atas, lalu jalankan lagi.
    pause
    exit /b 1
  )
  echo ok > ".installed"
  echo.
)

:: --- 2. Pastikan Python & library ---
where uv >nul 2>nul
if errorlevel 1 (
  echo  [*] Install uv...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
uv python install 3.12 >nul 2>&1
uv pip install --python 3.12 -q gspread google-auth python-dotenv requests
for /f "delims=" %%P in ('uv python find 3.12') do set PY=%%P

:: --- 3. Cek ADB & HP ---
adb start-server >nul 2>&1
for /f "tokens=1" %%A in ('adb devices ^| findstr /r "device$"') do set ADB_OK=1
if not defined ADB_OK (
  echo  [!] HP tidak terdeteksi via ADB.
  echo      Cek WiFi, Wireless debugging, lalu: adb connect IP:PORT
  echo      (lihat panduan di README.md)
  echo.
  pause
  exit /b 1
)

:: --- 4. Jalan! ---
echo.
echo  Semua siap. Uploader jalan (cek antrean tiap 10 menit).
echo  JANGAN tutup jendela ini. Tekan Ctrl+C untuk berhenti.
echo.
"%PY%" uploader.py --loop
pause
