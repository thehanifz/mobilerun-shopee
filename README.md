# Shopee Video Uploader Agent — Mobilerun (dulu DroidRun) + 9Router

Otomatisasi upload video affiliate ke **Shopee Video** memakai HP Android sendiri
yang digerakkan AI. Video tetap di-upload dari aplikasi Shopee resmi di HP
(via ADB wireless), jadi tidak butuh API seller.

## Cara tercepat (1 perintah)

1. Extract ZIP ke mis. `C:\shopee-uploader`
2. Salin `config.example.env` → `.env`, isi (IP 9Router, IP HP, Sheet ID, dll.)
3. Double-click **`start.bat`** — selesai. Pertama kali jalan otomatis:
   install (uv, Python, ADB, Mobilerun), pairing HP via WiFi, install Portal APK.
   Selanjutnya langsung jalan, cek antrean tiap 10 menit.

## Arsitektur

```
┌─────────────────────────────────────────────────────────────┐
│  Google Sheet "Daftar video afiliet"  (antrean)              │
│  Kolom: Judul+tag(≤150) | Link video Drive | Waktu upload   │
│         | Status | Error                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │ dibaca tiap 10 menit
┌──────────────────────▼──────────────────────────────────────┐
│  PC Windows — uploader.py  (Task Scheduler)                 │
│   1. Ambil baris Status="belum upload" & Waktu upload tiba  │
│   2. Tandai "sedang upload"                                 │
│   3. Download MP4 dari Drive → adb push ke HP               │
│   4. mobilerun run "upload video X ke Shopee Video..."      │
│   5. Tandai "done upload" / "gagal" + pesan Error           │
└──────┬──────────────────────────────────┬───────────────────┘
       │ ADB wireless (WiFi)               │ HTTP (LAN/Tailscale)
┌──────▼──────────────┐        ┌───────────▼──────────────────┐
│ HP Android          │        │ Server kamu: 9Router         │
│ Shopee app (login   │        │ (OpenAI-compatible, model    │
│ affiliate), Portal  │        │ vision-capable, mis. gratis) │
│ APK, Shopee login   │        └──────────────────────────────┘
└─────────────────────┘
```

**Kenapa begini?** Phone Link Win 11 tidak punya API otomasi (cuma mirroring
manual). ADB + Mobilerun = AI melihat layar HP (screenshot + accessibility
tree) lalu tap/swipe/ketik sendiri. 9Router jadi "otak" via endpoint
OpenAI-compatible — Mobilerun resmi mendukung model OpenAI-compatible.

## File di folder ini

| File | Fungsi |
|---|---|
| `start.bat` | **Pintu masuk utama** — double-click, beres (setup otomatis bila baru) |
| `setup_pc.ps1` | Instalasi detail (dipanggil otomatis oleh start.bat saat pertama kali) |
| `config.example.env` | Contoh konfigurasi → salin jadi `.env` lalu isi |
| `uploader.py` | Orkestrator utama (jadwal via Task Scheduler tiap 10 mnt) |
| `app_card_shopee.md` | Panduan UI Shopee untuk agen (App Card) |
| `queue_example.csv` | Contoh format antrean |

## Setup (sekali saja)

1. **Di HP Android:** aktifkan Developer options (tap Build number 7x) →
   nyalakan **Wireless debugging**. Hubungkan HP & PC ke WiFi yang sama.
   Pastikan aplikasi Shopee sudah login akun affiliate.
2. **Di server kamu:** pastikan 9Router bisa diakses dari PC
   (satu LAN, atau via Tailscale). Catat `http://IP-SERVER:20128/v1`
   dan siapkan model yang **bisa vision** (agen butuh lihat screenshot).
3. **Di PC:** klik kanan `setup_pc.ps1` → Run with PowerShell (boleh sebagai
   admin). Script menginstal uv, Python 3.12, platform-tools (ADB),
   Mobilerun, lalu pairing HP (`adb pair`) + instal Portal APK
   (`mobilerun setup`) + tes koneksi (`mobilerun ping`).
4. **LLM (cara pasti — terverifikasi 29 Okt):** 9Router itu OpenAI-compatible,
   jadi di `mobilerun configure` pilih provider **OpenAI**, isi API key
   9Router dan nama model vision persis seperti di dashboard 9Router.
   Base URL **tidak perlu** diisi di wizard — `uploader.py` otomatis
   meng-inject `OPENAI_BASE_URL` (= `LLM_BASE_URL` di `.env`) dan
   `OPENAI_API_KEY` (= `LLM_API_KEY`) ke setiap pemanggilan
   `mobilerun run` (SDK OpenAI membaca kedua env var ini secara native).
   Untuk tes manual tanpa wizard:
   `mobilerun run "What app is currently open?" --provider openai --model
   <nama-model> --base_url http://IP-SERVER:20128/v1`
   dengan `OPENAI_API_KEY` ter-set di environment.
5. **Google Sheet:** buat Service Account di Google Cloud, download JSON-nya,
   share sheet "Daftar video afiliet" ke email service account itu
   (akses Editor). Isi path JSON di `.env`.
6. **Task Scheduler:** buat task "ShopeeUploader" → trigger tiap 10 menit →
   action `pythonw.exe C:\shopee-uploader\uploader.py`. Atau jalankan manual
   untuk tes pertama: `python uploader.py --once`.

## Pengaman (anti-ban)

- Maks **8 upload/hari**, jeda acak **20–45 menit** antar upload
- Hanya jalan **07:00–21:00 WIB**
- Tiap video dicoba maks **2x**, selebihnya ditandai `gagal` + pesan error
- Mulai dari **akun kecil / 2–3 video per hari** di minggu pertama,
  naikkan bertahap kalau aman

## Status di Sheet (kontrak)

`belum upload` → (uploader) → `sedang upload` → `done upload` / `gagal`
(+ kolom `Error` diisi pesan kegagalan). Kamu/Muse hanya menulis sampai
`belum upload`.
