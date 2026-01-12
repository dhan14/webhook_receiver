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

# --- 1. SETUP & UTILS ENVIRONMENT ---

def setup_environment() -> Tuple[str, str, str, str]:
    """Memuat variabel environment dan mengembalikannya."""
    load_dotenv() 
    wa_api_url = os.getenv("WA_API_URL", "http://localhost:3000/send/message")
    wa_reconnect_url = os.getenv("WA_RECONNECT_URL", "http://localhost:3000/app/reconnect")
    wa_username = os.getenv("WA_USER", "default_user") 
    wa_password = os.getenv("WA_PASS", "default_pass")
    return wa_api_url, wa_reconnect_url, wa_username, wa_password

# Ambil variabel ENV saat startup
WHATSAPP_API_URL, WHATSAPP_RECONNECT_URL, WHATSAPP_USERNAME, WHATSAPP_PASSWORD = setup_environment()

# Inisialisasi FastAPI
app = FastAPI(
    title="Webhook Receiver",
    description="Meneruskan notifikasi Uptime Kuma ke layanan Go WhatsApp",
    version="1.0.1"
)

# --- 2. FUNGSI PARSING & STATUS ---

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


# --- 3. FUNGSI LOGIKA WHATSAPP (RECONNECT & RETRY) ---

async def _perform_wa_request(client: httpx.AsyncClient, url: str, payload: Dict[str, Any], is_reconnect: bool = False):
    """Fungsi pembantu untuk melakukan POST request ke endpoint WA API."""
    auth_tuple = (WHATSAPP_USERNAME, WHATSAPP_PASSWORD)
    json_data = payload if not is_reconnect else None
    
    response = await client.post(
        url,
        json=json_data,
        auth=auth_tuple
    )
    return response

async def send_whatsapp_notification_phone(phone_number: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Go WhatsApp dengan logika retry 401."""
    
    whatsapp_payload = {
        "phone": f"{phone_number}@s.whatsapp.net",
        "message": text_message,
        "is_forwarded": False
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ATTEMPT 1
        try:
            response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)
            
            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim (Percobaan 1). Status: {response.status_code}")
                return True, response.json()
            
            elif response.status_code == 401:
                logging.warning("⚠️ Otorisasi WA GAGAL (401). Mencoba Reconnect dan Retry...")
                
                # RECONNECT STEP
                reconnect_response = await _perform_wa_request(client, WHATSAPP_RECONNECT_URL, {}, is_reconnect=True)
                
                if reconnect_response.status_code >= 200 and reconnect_response.status_code < 300:
                    logging.info("✅ Reconnect ke WA API Sukses. Mencoba kirim ulang pesan...")
                    
                    # ATTEMPT 2
                    retry_response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)
                    
                    if retry_response.status_code >= 200 and retry_response.status_code < 300:
                        logging.info(f"✅ Notifikasi WA berhasil dikirim (Percobaan 2). Status: {retry_response.status_code}")
                        return True, retry_response.json()
                    else:
                        logging.error(f"❌ Gagal kirim WA setelah Reconnect. Status: {retry_response.status_code}")
                        return False, {"error": "Failed after reconnect retry", "detail": retry_response.text}
                else:
                    logging.error(f"❌ Reconnect ke WA API GAGAL. Status: {reconnect_response.status_code}")
                    return False, {"error": "Reconnect failed", "detail": reconnect_response.text}

            else:
                logging.error(f"❌ Gagal kirim notifikasi WA (Non-401). Status: {response.status_code}")
                return False, {"error": "Failed to send WA message", "detail": response.text}
                
        except httpx.RequestError as e:
            logging.critical(f"❌ Error koneksi ke Go WhatsApp API: {e}")
            return False, {"error": "Connection error to WA API"}

async def send_whatsapp_notification_group(group_id: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Go WhatsApp dengan logika retry 401."""

    whatsapp_payload = {
        "phone": f"{group_id}@g.us",
        "message": text_message,
        "is_forwarded": False
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ATTEMPT 1
        try:
            response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)

            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim ke grup (Percobaan 1). Status: {response.status_code}")
                return True, response.json()

            elif response.status_code == 401:
                logging.warning("⚠ Otorisasi WA GAGAL (401). Mencoba Reconnect dan Retry...")

                # RECONNECT STEP
                reconnect_response = await _perform_wa_request(client, WHATSAPP_RECONNECT_URL, {}, is_reconnect=True)

                if reconnect_response.status_code >= 200 and reconnect_response.status_code < 300:
                    logging.info("✅ Reconnect ke WA API Sukses. Mencoba kirim ulang pesan...")

                    # ATTEMPT 2
                    retry_response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)

                    if retry_response.status_code >= 200 and retry_response.status_code < 300:
                        logging.info(f"✅ Notifikasi WA berhasil dikirim ke grup (Percobaan 2). Status: {retry_response.status_code}")
                        return True, retry_response.json()
                    else:
                        logging.error(f"❌ Gagal kirim WA setelah Reconnect. Status: {retry_response.status_code}")
                        return False, {"error": "Failed after reconnect retry", "detail": retry_response.text}
                else:
                    logging.error(f"❌ Reconnect ke WA API GAGAL. Status: {reconnect_response.status_code}")
                    return False, {"error": "Reconnect failed", "detail": reconnect_response.text}

            else:
                logging.error(f"❌ Gagal kirim notifikasi WA (Non-401). Status: {response.status_code}")
                return False, {"error": "Failed to send WA message", "detail": response.text}

        except httpx.RequestError as e:
            logging.critical(f"❌ Error koneksi ke Go WhatsApp API: {e}")
            return False, {"error": "Connection error to WA API"}


# --- 4. ENDPOINT UTAMA (Mengkoordinasikan semua fungsi) ---

@app.post("/webhook/uptime-kuma/phone", response_model=None) 
async def handle_uptime_kuma_webhook_phone(request: Request): 
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
            
            wa_success, wa_result = await send_whatsapp_notification_phone(
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

@app.post("/webhook/uptime-kuma/group", response_model=None)
async def handle_uptime_kuma_webhook_group(request: Request):
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
    target_whatsapp_phone = payload.get("for_whatsapp", "GID_TIDAK_ADA")


    # 3. Pengiriman Notifikasi (Hanya jika DOWN/ERROR ATAU TESTING)
    wa_success = False
    wa_result = {}

    # Notifikasi dikirim JIKA: Status BUKAN UP (DOWN/ERROR) ATAU Status adalah TESTING
    should_send_notification = not is_up or is_testing


    if target_whatsapp_phone != "GID_TIDAK_ADA":

        if should_send_notification:

            log_status = "DOWN/Error" if not is_up else "TESTING"
            logging.info(f"🚨 Status {log_status} terdeteksi. Mengirim notifikasi...")

            wa_success, wa_result = await send_whatsapp_notification_group(
                group_id=target_whatsapp_phone,
                text_message=notification_text
            )
        else:
            # Jika status UP dan BUKAN TESTING, notifikasi dilewati.
            logging.info("ℹ Status UP terdeteksi, dan BUKAN TESTING. Notifikasi WhatsApp dilewati.")
            wa_success = True
            wa_result = {"status": "skipped", "reason": "Service is UP, notification suppressed"}
    else:
        logging.warning("Group ID WhatsApp tidak ditemukan di payload ('for_whatsapp'). Notifikasi WA dilewatkan.")


    return {
        "message": "Webhook DITERIMA, cek wa_sent untuk status notifikasi WA.",
        "service_status_identified": "UP (Skipped)" if not should_send_notification else ("DOWN" if not is_up else "TESTING"),
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }

# Endpoint untuk testing dasar
@app.get("/")
def read_root():
    return {"message": "Webhook Bridge Aktif di Port 3031"}
