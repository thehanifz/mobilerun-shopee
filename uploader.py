#!/usr/bin/env python3
"""
Shopee Video Uploader Agent — orkestrator.

Dijalankan tiap 10 menit via Windows Task Scheduler (atau manual --once).
Alur per video:
  Sheet (belum upload & waktunya tiba) -> download MP4 -> adb push ke HP
  -> mobilerun (AI) upload via aplikasi Shopee -> update Status di Sheet.

Butuh: pip install gspread google-auth python-dotenv requests
Env: lihat config.example.env  (salin jadi .env)
"""
import argparse, csv, json, os, random, re, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------- Konfigurasi ----------
BASE = Path(__file__).resolve().parent
ENV_PATH = BASE / ".env"

def load_env(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_env(ENV_PATH)
def E(k, default=""):
    return os.environ.get(k, ENV.get(k, default))

WORK = Path(E("WORK_DIR", str(BASE / "work"))); WORK.mkdir(parents=True, exist_ok=True)
STATE_PATH = WORK / "state.json"

# Nama kolom di Google Sheet (sesuaikan bila header diubah)
C_TITLE   = "Judul + tag (≤150)"
C_DRIVE   = "Link video Drive"
C_TIME    = "Waktu upload"
C_STATUS  = "Status"
C_ERROR   = "Error"
C_CAPTION = "Caption"

S_READY, S_BUSY, S_DONE, S_FAIL = "belum upload", "sedang upload", "done upload", "gagal"

# ---------- State lokal (kuota harian & retry) ----------
def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"day": "", "done_today": 0, "retry": {}}

def save_state(s):
    STATE_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")

# ---------- Google Sheet ----------
def get_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(E("GOOGLE_SA_JSON"), scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(E("SHEET_ID")).worksheet(E("WORKSHEET", "Sheet1"))

def parse_time(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

# ---------- ADB & download ----------
def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def adb(*args):
    return sh(["adb", "-s", E("ADB_DEVICE"), *args])

def download_video(url, dest):
    # Link Drive langsung (uc?export=download) atau URL file biasa
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest

def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s)[:60]

# ---------- Mobilerun ----------
TASK_TEMPLATE = """Buka aplikasi Shopee di HP ini. Upload video berikut ke Shopee Video:
- File video: {phone_path} (sudah ada di folder Download HP)
- Caption/deskripsi: {caption}

Langkah: buka Shopee > tab Video > tombol + / Upload > pilih file video tersebut >
isi caption persis seperti di atas > tautkan/keranjang produk yang relevan bila
ada tombolnya > bila ada toggle/opsi "konten AI" atau "AI-generated", AKTIFKAN
(aturan Shopee: video AI wajib diberi label) > posting/upload videonya. Tunggu
sampai upload selesai dan kembali ke halaman Video. Jangan buka aplikasi lain.
Bila muncul login, captcha, atau error, hentikan dan laporkan apa yang terjadi."""

def run_mobilerun(task):
    env = dict(os.environ)
    env["OPENAI_BASE_URL"] = E("LLM_BASE_URL")
    env["OPENAI_API_KEY"] = E("LLM_API_KEY")
    # Model di-pick dari `mobilerun configure`; flag --model bila didukung versi kamu.
    p = subprocess.run(
        ["mobilerun", "run", task, "--vision", "--steps", "40"],
        capture_output=True, text=True, timeout=1800, env=env,
        cwd=str(BASE),
    )
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    return p.returncode == 0, out[-3000:]

# ---------- Main ----------
def run_cycle(args):
    now = datetime.now()
    st = load_state()
    today = now.strftime("%Y-%m-%d")
    if st["day"] != today:
        st = {"day": today, "done_today": 0, "retry": {}}

    max_up = int(E("MAX_UPLOADS_PER_DAY", "8"))
    h0, h1 = int(E("ACTIVE_HOUR_START", "7")), int(E("ACTIVE_HOUR_END", "21"))
    if not (h0 <= now.hour < h1):
        print(f"Di luar jam aktif ({h0}:00-{h1}:00), skip.")
        return

    ws = get_sheet()
    rows = ws.get_all_records()
    headers = ws.row_values(1)
    i_status, i_error = headers.index(C_STATUS) + 1, headers.index(C_ERROR) + 1

    due = []
    for idx, r in enumerate(rows, start=2):
        if (r.get(C_STATUS) or "").strip() != S_READY:
            continue
        t = parse_time(r.get(C_TIME))
        if t and t <= now:
            due.append((idx, r))
    due.sort(key=lambda x: parse_time(x[1].get(C_TIME)) or now)
    print(f"Antrean jatuh tempo: {len(due)} video.")

    if args.dry:
        for idx, r in due:
            print(f" - baris {idx}: {r.get(C_TITLE,'')[:60]}")
        return

    quota = max_up - st["done_today"]
    for idx, r in due[:max(quota, 0)]:
        title = (r.get(C_TITLE) or r.get(C_CAPTION) or "video").strip()
        key = f"row{idx}"
        tries = st["retry"].get(key, 0)
        print(f"\n>> Proses baris {idx}: {title[:60]} (percobaan {tries+1})")
        ws.update_cell(idx, i_status, S_BUSY)
        try:
            fname = safe_name(title) + ".mp4"
            local = WORK / fname
            print("   download video...")
            download_video(r[C_DRIVE], local)
            print("   push ke HP...")
            phone_path = f"/sdcard/Download/{fname}"
            rr = adb("push", str(local), phone_path)
            if rr.returncode != 0:
                raise RuntimeError("adb push gagal: " + rr.stderr[-500:])
            # beri HP waktu indexing media
            sh(["adb", "-s", E("ADB_DEVICE"), "shell",
                "am", "broadcast", "-a",
                "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file://{phone_path}"])
            time.sleep(5)
            caption = (r.get(C_CAPTION) or r.get(C_TITLE) or "").strip()[:150]
            print("   mobilerun mengupload via aplikasi Shopee...")
            ok, log = run_mobilerun(TASK_TEMPLATE.format(
                phone_path=phone_path, caption=caption))
            if not ok:
                raise RuntimeError("mobilerun gagal:\n" + log)
            ws.update_cell(idx, i_status, S_DONE)
            ws.update_cell(idx, i_error, "")
            st["done_today"] += 1
            st["retry"].pop(key, None)
            print("   OK -> done upload")
        except Exception as e:
            tries += 1
            st["retry"][key] = tries
            msg = str(e)[-500:]
            if tries >= int(E("MAX_RETRY", "2")):
                ws.update_cell(idx, i_status, S_FAIL)
                ws.update_cell(idx, i_error, msg)
                print(f"   GAGAL permanen -> {msg}")
            else:
                ws.update_cell(idx, i_status, S_READY)  # coba lagi siklus berikut
                ws.update_cell(idx, i_error, f"retry {tries}: {msg}")
                print(f"   gagal, dijadwalkan retry -> {msg}")
        save_state(st)
        # jeda manusiawi antar upload
        if due.index((idx, r)) < len(due[:quota]) - 1:
            delay = random.randint(int(E("MIN_DELAY_MIN", "20")),
                                   int(E("MAX_DELAY_MIN", "45")))
            print(f"   jeda {delay} menit sebelum video berikut...")
            time.sleep(delay * 60)

    save_state(st)
    print(f"\nSelesai. Upload hari ini: {st['done_today']}/{max_up}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="satu siklus lalu keluar")
    ap.add_argument("--loop", action="store_true",
                    help="jalan terus, cek antrean tiap 10 menit (dipakai start.bat)")
    ap.add_argument("--dry", action="store_true", help="cek antrean tanpa eksekusi")
    args = ap.parse_args()

    if args.loop:
        print("Mode loop: cek antrean tiap 10 menit. Ctrl+C untuk berhenti.\n")
        while True:
            try:
                run_cycle(args)
            except Exception as e:
                print(f"[loop] error siklus: {e}")
            print("\nTidur 10 menit...\n")
            time.sleep(600)
    else:
        run_cycle(args)

if __name__ == "__main__":
    sys.exit(main())
