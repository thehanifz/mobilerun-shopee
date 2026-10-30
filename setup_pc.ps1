<#
.SYNOPSIS
  Setup sekali saja: Shopee Video Uploader Agent di PC Windows.
  Menginstal: uv + Python 3.12, Android platform-tools (ADB),
  Mobilerun (dulu DroidRun), pairing HP via WiFi, Portal APK.
.NOTES
  Jalankan: klik kanan > Run with PowerShell (disarankan sebagai admin).
  HP Android & PC harus di WiFi yang sama, Wireless debugging sudah nyala.
#>
$ErrorActionPreference = "Stop"
$BaseDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
New-Item -ItemType Directory -Force -Path "$BaseDir\work" | Out-Null
Set-Location $BaseDir

Write-Host "== 1/6 Install uv ==" -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "== 2/6 Install Python 3.12 ==" -ForegroundColor Cyan
uv python install 3.12

Write-Host "== 3/6 Download Android platform-tools (ADB) ==" -ForegroundColor Cyan
$ptools = "$BaseDir\platform-tools"
if (-not (Test-Path "$ptools\adb.exe")) {
    $zip = "$BaseDir\platform-tools.zip"
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $BaseDir -Force
    Remove-Item $zip
}
$env:Path = "$ptools;$env:Path"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$ptools*") {
    [Environment]::SetEnvironmentVariable("Path", "$ptools;$userPath", "User")
}
adb version

Write-Host "== 4/6 Install Mobilerun ==" -ForegroundColor Cyan
uv tool install mobilerun
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

Write-Host "== 5/6 Pairing HP via WiFi ==" -ForegroundColor Cyan
Write-Host "Di HP: Settings > Developer options > Wireless debugging > 'Pair device with pairing code'"
$pairIp = Read-Host "Masukkan IP pairing HP (mis. 192.168.1.20)"
$pairPort = Read-Host "Masukkan port pairing (mis. 37001)"
$pairCode = Read-Host "Masukkan 6 digit pairing code"
adb pair "$pairIp`:$pairPort" $pairCode

Write-Host "Sekarang di HP lihat IP & port Wireless debugging utama (bukan pairing), mis. 192.168.1.20:5555"
$devAddr = Read-Host "Masukkan IP:PORT device (untuk .env -> ADB_DEVICE)"
adb connect $devAddr
adb devices

Write-Host "== 6/6 Install Portal APK & tes ==" -ForegroundColor Cyan
mobilerun setup
mobilerun ping

Write-Host ""
Write-Host "SELESAI." -ForegroundColor Green
Write-Host "Alamat device HP kamu: $devAddr  -> tulis ke .env (ADB_DEVICE)"
Write-Host "Lanjut: 1) salin config.example.env jadi .env dan isi"
Write-Host "       2) mobilerun configure  (provider OpenAI-compatible -> 9Router)"
Write-Host "       3) siapkan service-account.json Google Sheet"
Write-Host "       4) tes: python uploader.py --once"
