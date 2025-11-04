# main.py
from fastapi import FastAPI, Request
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
import json
import logging
import httpx 
import os 
import re 
from dotenv import load_dotenv

# 1. Muat .env di awal
load_dotenv() 

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inisialisasi FastAPI
app = FastAPI(
    title="Webhook Bridge FastAPI",
    description="Meneruskan notifikasi Uptime Kuma ke layanan Go WhatsApp",
    version="1.0.0"
)

# Ambil nilai dari .env (dengan fallback)
WHATSAPP_API_URL = os.getenv("WA_API_URL", "http://localhost:3000/send/message")
WHATSAPP_RECONNECT_URL = os.getenv("WA_RECONNECT_URL", "http://localhost:3000/app/reconnect")
WHATSAPP_USERNAME = os.getenv("WA_USER", "default_user") 
WHATSAPP_PASSWORD = os.getenv("WA_PASS", "default_pass")
# -----------------------------------

# Fungsi pembantu untuk melakukan request HTTP ke WA API
async def _perform_wa_request(client: httpx.AsyncClient, url: str, payload: Dict[str, Any], is_reconnect: bool = False):
    """
    Melakukan POST request ke endpoint WA API.
    """
    auth_tuple = (WHATSAPP_USERNAME, WHATSAPP_PASSWORD)
    json_data = payload if not is_reconnect else None
    
    response = await client.post(
        url,
        json=json_data,
        auth=auth_tuple
    )
    return response

# Fungsi utama dengan logika retry dan reconnect
async def send_whatsapp_notification(phone_number: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Go WhatsApp dengan logika retry."""
    
    whatsapp_payload = {
        "phone": f"{phone_number}@s.whatsapp.net",
        "message": text_message,
        "is_forwarded": False
    }

    # Menggunakan timeout yang wajar untuk request eksternal
    async with httpx.AsyncClient(timeout=15.0) as client:
        # --- ATTEMPT 1: Kirim Pesan Pertama ---
        try:
            response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)
            
            # Jika berhasil (kode 2xx)
            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim (Percobaan 1). Status: {response.status_code}")
                return True, response.json()
            
            # Jika Gagal Otorisasi (401)
            elif response.status_code == 401:
                logging.warning("⚠️ Otorisasi WA GAGAL (401). Mencoba Reconnect dan Retry...")
                
                # --- RECONNECT STEP ---
                # Payload reconnect dikosongkan (dict kosong)
                reconnect_response = await _perform_wa_request(client, WHATSAPP_RECONNECT_URL, {}, is_reconnect=True)
                
                if reconnect_response.status_code >= 200 and reconnect_response.status_code < 300:
                    logging.info("✅ Reconnect ke WA API Sukses. Mencoba kirim ulang pesan...")
                    
                    # --- ATTEMPT 2: Kirim Ulang Pesan ---
                    retry_response = await _perform_wa_request(client, WHATSAPP_API_URL, whatsapp_payload)
                    
                    if retry_response.status_code >= 200 and retry_response.status_code < 300:
                        logging.info(f"✅ Notifikasi WA berhasil dikirim (Percobaan 2). Status: {retry_response.status_code}")
                        return True, retry_response.json()
                    else:
                        # Retry Gagal
                        logging.error(f"❌ Gagal kirim WA setelah Reconnect. Status: {retry_response.status_code}")
                        return False, {"error": "Failed after reconnect retry", "detail": retry_response.text}
                else:
                    # Reconnect Gagal
                    logging.error(f"❌ Reconnect ke WA API GAGAL. Status: {reconnect_response.status_code}")
                    return False, {"error": "Reconnect failed", "detail": reconnect_response.text}

            else:
                # Gagal karena kode status lain (400, 500, dll.)
                logging.error(f"❌ Gagal kirim notifikasi WA (Non-401). Status: {response.status_code}")
                return False, {"error": "Failed to send WA message", "detail": response.text}
                
        except httpx.RequestError as e:
            logging.critical(f"❌ Error koneksi ke Go WhatsApp API: {e}")
            return False, {"error": "Connection error to WA API"}


# FUNGSI ENDPOINT UTAMA
@app.post("/webhook/uptime-kuma", response_model=None) 
async def handle_uptime_kuma_webhook(request: Request): 
    
    # --- 1. Sanitasi dan Parsing Body ---
    raw_body = await request.body()
    raw_body_str = raw_body.decode('utf-8').strip()
    
    payload = {}
    try:
        payload = json.loads(raw_body_str)
        logging.info("✅ Payload JSON valid dan berhasil diparse.")
        
    except json.JSONDecodeError:
        logging.warning("❌ Payload JSON tidak valid. Mencoba sanitasi manual...")
        
        # Sanitasi: Mengganti key 'status' yang hilang quotes menjadi '"status":'
        sanitized_str = raw_body_str
        if 'status:' in raw_body_str and not '"status":' in raw_body_str:
            sanitized_str = raw_body_str.replace('status:', '"status":')

        try:
            # Hapus newlines dan tabs sebelum final parse
            sanitized_str = sanitized_str.replace('\n', '').replace('\t', '')
            payload = json.loads(sanitized_str)
            logging.info("✅ Sanitasi berhasil dan payload diparse.")

        except json.JSONDecodeError as e:
            logging.error(f"❌ Sanitasi gagal total. Webhook body tidak dapat diproses: {e}")
            return {"message": "Gagal memproses Webhook: JSON tidak valid", "wa_sent": False, "raw_body": raw_body_str}

    # --- 2. Pemrosesan Data dan Logika Status ---
    logging.info("--- Payload Webhook Diterima ---")
    print(json.dumps(payload, indent=4))
    
    status_field = str(payload.get("status", ""))
    description = payload.get("description", "Detail tidak tersedia.")
    target_whatsapp_number = payload.get("for_whatsapp", "NOMOR_TIDAK_ADA")
    
    
    # Penentuan Timestamp Real-Time (WIB)
    wib_tz = timezone(timedelta(hours=7))
    current_time_wib = datetime.now(wib_tz).strftime("%d-%m-%Y %H:%M:%S WIB")
    
    
    # Logika Status yang Lebih Andal
    is_up = False
    
    # Cek untuk status UP (Up, OK, atau simbol ✅)
    if "up" in status_field.lower() or "ok" in status_field.lower() or "✅" in description:
        is_up = True
    elif "down" in status_field.lower() or "failed" in status_field.lower() or "🔴" in description or "error" in status_field.lower():
        is_up = False
    else:
        # Fallback: Coba ekstraksi kode angka atau cek string kosong
        match = re.search(r'^\d{3}', status_field)
        if (match and int(match.group(0)) < 400) or status_field.strip() == "":
             is_up = True
        else:
             is_up = False 
    
    
    # Tentukan Pesan Notifikasi 
    if is_up:
        # Pesan UP statis dengan timestamp
        notification_text = f"✅ Layanan telah kembali normal pada: **{current_time_wib}**\n\nDetail: {description}"
    else:
        # Tampilkan detail error untuk status DOWN
        notification_text = f"🚨 Layanan mengalami masalah pada: **{current_time_wib}**\n\nDetail Error: {description}"
    
    
    # --- 3. Kirim Notifikasi ke Go WhatsApp ---
    wa_success = False
    wa_result = {}
    
    if target_whatsapp_number != "NOMOR_TIDAK_ADA":
        wa_success, wa_result = await send_whatsapp_notification(
            phone_number=target_whatsapp_number, 
            text_message=notification_text
        )
    else:
        logging.warning("Nomor WhatsApp tidak ditemukan di payload ('for_whatsapp'). Notifikasi WA dilewatkan.")


    return {
        "message": "Webhook DITERIMA, cek wa_sent untuk status notifikasi WA.",
        "service_status_identified": "UP" if is_up else "DOWN",
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }

# Endpoint untuk testing dasar
@app.get("/")
def read_root():
    return {"message": "Webhook Bridge Aktif di Port 3010"}
