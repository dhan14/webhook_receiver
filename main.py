# main.py
from fastapi import FastAPI, Request
from typing import Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import json
import logging
import httpx
import os
import re
from dotenv import load_dotenv

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 1. SETUP & UTILS ENVIRONMENT (Disesuaikan untuk Waha) ---

def setup_environment() -> Tuple[str, str, str]:
    """Memuat variabel environment dan mengembalikannya untuk Waha."""
    load_dotenv()
    # Base URL Waha (misal: http://93.127.199.92:3000/api)
    wa_base_url = os.getenv("WA_BASE_URL", "http://localhost:3000/api")
    # Session Waha (misal: default)
    wa_session_name = os.getenv("WA_SESSION", "default")
    # API Key Waha (Opsional, jika Waha menggunakan otentikasi)
    wa_api_key = os.getenv("WA_API_KEY", "") 
    return wa_base_url, wa_session_name, wa_api_key

# Ambil variabel ENV saat startup (Variabel lama yang tidak relevan dihapus)
WHATSAPP_BASE_URL, WHATSAPP_SESSION, WHATSAPP_API_KEY = setup_environment()

# Inisialisasi FastAPI
app = FastAPI(
    title="Webhook Bridge FastAPI (WAHA Ready)",
    description="Meneruskan notifikasi Uptime Kuma ke layanan Waha",
    version="1.0.0"
)

# --- 2. FUNGSI PARSING & STATUS (Tidak Berubah) ---

def sanitize_and_parse_payload(raw_body_str: str) -> Dict[str, Any] | None:
    """Mencoba parsing JSON, dan melakukan sanitasi manual jika gagal (untuk Uptime Kuma)."""
    payload = {}
    try:
        payload = json.loads(raw_body_str)
        logging.info("✅ Payload JSON valid dan berhasil diparse.")
        return payload
    except json.JSONDecodeError:
        logging.warning("❌ Payload JSON tidak valid. Mencoba sanitasi manual...")

        sanitized_str = raw_body_str
        # Perbaikan: key 'status' yang hilang quotes
        if 'status:' in raw_body_str and not '"status":' in raw_body_str:
            sanitized_str = raw_body_str.replace('status:', '"status":')

        try:
            # Hapus newlines/tabs sebelum final parse
            sanitized_str = sanitized_str.replace('\n', '').replace('\t', '')
            payload = json.loads(sanitized_str)
            logging.info("✅ Sanitasi berhasil dan payload diparse.")
            return payload
        except json.JSONDecodeError as e:
            logging.error(f"❌ Sanitasi gagal total. Webhook body tidak dapat diproses: {e}")
            return None

def determine_status_and_text(payload: Dict[str, Any]) -> Tuple[bool, str, str, bool]:
    """Menentukan status UP/DOWN, is_testing, dan membuat teks notifikasi dengan timestamp."""

    status_field = str(payload.get("status", ""))
    description = payload.get("description", "Detail tidak tersedia.")

    # Penentuan Timestamp Real-Time (WIB)
    wib_tz = timezone(timedelta(hours=7))
    current_time_wib = datetime.now(wib_tz).strftime("%d-%m-%Y %H:%M:%S WIB")

    is_up = False

    # Logika Status yang Lebih Andal
    if "up" in status_field.lower() or "ok" in status_field.lower() or "✅" in description:
        is_up = True
    elif "down" in status_field.lower() or "failed" in status_field.lower() or "🔴" in description or "error" in status_field.lower():
        is_up = False
    else:
        # Fallback: Coba ekstraksi kode angka atau cek string kosong
        match = re.search(r'^\d{3}', status_field)
        if (match and int(match.group(0)) < 400) or status_field.strip() == "":
            is_up = True # Anggap UP jika status kosong (default Uptime Kuma)
        else:
            is_up = False

    # Pengecekan Testing
    is_testing = "test" in description.lower() or "testing" in description.lower()


    # Tentukan Pesan Notifikasi
    if is_up:
        notification_text = f"✅ Layanan telah kembali normal pada: **{current_time_wib}**\n\nDetail: {description}"
    else:
        notification_text = f"🚨 Layanan mengalami masalah pada: **{current_time_wib}**\n\nDetail Error: {description}"


    return is_up, notification_text, status_field, is_testing


# --- 3. FUNGSI LOGIKA WHATSAPP (Waha Simple Send) ---

async def send_whatsapp_notification(phone_number: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Waha (sendText) dengan query params."""

    # Payload dikonversi ke query parameters
    params = {
        "phone": phone_number,
        "text": text_message,
        "session": WHATSAPP_SESSION,
    }
    
    # Tambahkan API Key jika ada
    if WHATSAPP_API_KEY:
        params["apiKey"] = WHATSAPP_API_KEY

    # Endpoint Waha spesifik
    wa_api_url = f"{WHATSAPP_BASE_URL}/sendText" 

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ATTEMPT 1 - Langsung kirim (Waha tidak memerlukan logika reconnect 401 seperti GoWA)
        try:
            # Menggunakan POST request ke URL dengan query parameters
            response = await client.post(
                wa_api_url,
                params=params 
            )

            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WAHA berhasil dikirim. Status: {response.status_code}")
                # Waha merespons dengan JSON, kita kembalikan hasilnya
                return True, response.json()

            else:
                logging.error(f"❌ Gagal kirim notifikasi WAHA. Status: {response.status_code}. Detail: {response.text}")
                return False, {"error": "Failed to send WAHA message", "detail": response.text}

        except httpx.RequestError as e:
            logging.critical(f"❌ Error koneksi ke WAHA API: {e}")
            return False, {"error": "Connection error to WAHA API"}


# --- 4. ENDPOINT UTAMA (Tidak Berubah) ---

@app.post("/webhook/uptime-kuma", response_model=None)
async def handle_uptime_kuma_webhook(request: Request):
    """Endpoint utama untuk menerima, memproses, dan meneruskan Webhook."""

    # 1. Parsing dan Sanitasi
    raw_body = await request.body()
    raw_body_str = raw_body.decode('utf-8').strip()

    payload = sanitize_and_parse_payload(raw_body_str)

    if payload is None:
        return {"message": "Gagal memproses Webhook: JSON tidak valid", "wa_sent": False, "raw_body": raw_body_str}

    # 2. Pemrosesan Logika
    logging.info("--- Payload Webhook Diterima ---")
    # print(json.dumps(payload, indent=4)) # Dapat dinonaktifkan di production

    is_up, notification_text, status_field, is_testing = determine_status_and_text(payload)
    target_whatsapp_number = payload.get("for_whatsapp", "NOMOR_TIDAK_ADA")


    # 3. Pengiriman Notifikasi (Hanya jika DOWN/ERROR ATAU TESTING)
    wa_success = False
    wa_result = {}

    # Notifikasi dikirim JIKA: Status BUKAN UP (DOWN/ERROR) ATAU Status adalah TESTING
    should_send_notification = not is_up or is_testing


    if target_whatsapp_number != "NOMOR_TIDAK_ADA":

        if should_send_notification:

            log_status = "DOWN/Error" if not is_up else "TESTING"
            logging.info(f"🚨 Status {log_status} terdeteksi. Mengirim notifikasi...")

            wa_success, wa_result = await send_whatsapp_notification(
                phone_number=target_whatsapp_number,
                text_message=notification_text
            )
        else:
            # Jika status UP dan BUKAN TESTING, notifikasi dilewati.
            logging.info("ℹ️ Status UP terdeteksi, dan BUKAN TESTING. Notifikasi WhatsApp dilewati.")
            wa_success = True
            wa_result = {"status": "skipped", "reason": "Service is UP, notification suppressed"}
    else:
        logging.warning("Nomor WhatsApp tidak ditemukan di payload ('for_whatsapp'). Notifikasi WA dilewatkan.")


    return {
        "message": "Webhook DITERIMA, cek wa_sent untuk status notifikasi WA.",
        "service_status_identified": "UP (Skipped)" if not should_send_notification else ("DOWN" if not is_up else "TESTING"),
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }

# Endpoint untuk testing dasar
@app.get("/")
def read_root():
    return {"message": "Webhook Bridge Aktif di Port 3010"}
