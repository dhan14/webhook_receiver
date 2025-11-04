# main.py
from fastapi import FastAPI, Request
from typing import Dict, Any
import json
import logging
import httpx 
from dotenv import load_dotenv
import os 
import re # Diperlukan untuk parsing status code

# 1. Muat .env di awal
load_dotenv() 

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inisialisasi FastAPI dengan argumen keyword yang benar
app = FastAPI(
    title="Webhook Bridge FastAPI",
    description="Meneruskan notifikasi Uptime Kuma ke layanan Go WhatsApp",
    version="1.0.0"
)

# Ambil nilai dari .env 
WHATSAPP_API_URL = os.getenv("WA_API_URL", "http://localhost:3000/send/message")
WHATSAPP_USERNAME = os.getenv("WA_USER", "default_user") 
WHATSAPP_PASSWORD = os.getenv("WA_PASS", "default_pass")
# -----------------------------------

# 2. FUNGSI PEMBANTU (Harus didefinisikan sebelum digunakan)
async def send_whatsapp_notification(phone_number: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Go WhatsApp."""
    
    # Payload yang akan dikirim ke Go WhatsApp (sesuai cURL Anda)
    whatsapp_payload = {
        "phone": f"{phone_number}@s.whatsapp.net",
        "message": text_message,
        "is_forwarded": False
    }

    try:
        # Menggunakan httpx.AsyncClient untuk koneksi asynchronous
        async with httpx.AsyncClient() as client:
            response = await client.post(
                WHATSAPP_API_URL,
                json=whatsapp_payload,
                # Menggunakan Basic Auth sesuai cURL --user "username:password"
                auth=(WHATSAPP_USERNAME, WHATSAPP_PASSWORD) 
            )
            
            # Cek jika request ke WhatsApp sukses (kode status 2xx)
            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim. Status: {response.status_code}")
                return True, response.json()
            else:
                logging.error(f"❌ Gagal kirim notifikasi WA. Status: {response.status_code}, Body: {response.text}")
                return False, {"error": "Failed to send WA message", "detail": response.text}
                
    except httpx.RequestError as e:
        logging.critical(f"❌ Error koneksi ke Go WhatsApp API: {e}")
        return False, {"error": "Connection error to WA API"}


# 3. FUNGSI ENDPOINT UTAMA
@app.post("/webhook/uptime-kuma", response_model=None) 
async def handle_uptime_kuma_webhook(request: Request): 
    """
    Menerima payload webhook, memproses status, dan meneruskan ke Go WhatsApp.
    Menggunakan Request object untuk menangani potensi JSON yang tidak valid.
    """
    
    # 1. Dapatkan body sebagai string mentah
    raw_body = await request.body()
    raw_body_str = raw_body.decode('utf-8').strip()
    
    payload = {}
    try:
        # Coba parse langsung
        payload = json.loads(raw_body_str)
        logging.info("✅ Payload JSON valid dan berhasil diparse.")
        
    except json.JSONDecodeError:
        logging.warning("❌ Payload JSON tidak valid. Mencoba sanitasi manual...")
        
        # Sanitasi: Mengganti key 'status' yang hilang quotes menjadi '"status":'
        sanitized_str = raw_body_str
        if 'status:' in raw_body_str and not '"status":' in raw_body_str:
            sanitized_str = raw_body_str.replace('status:', '"status":')

        try:
            # Mengganti baris baru dan tab agar parsing lebih mudah
            sanitized_str = sanitized_str.replace('\n', '').replace('\t', '')
            payload = json.loads(sanitized_str)
            logging.info("✅ Sanitasi berhasil dan payload diparse.")

        except json.JSONDecodeError as e:
            logging.error(f"❌ Sanitasi gagal total. Webhook body tidak dapat diproses: {e}")
            return {"message": "Gagal memproses Webhook: JSON tidak valid", "wa_sent": False, "raw_body": raw_body_str}

    # --- LANJUTKAN LOGIKA PEMROSESAN ---
    logging.info("--- Payload Webhook Diterima ---")
    print(json.dumps(payload, indent=4))
    
    status_field = str(payload.get("status", ""))
    description = payload.get("description", "Detail tidak tersedia.")
    target_whatsapp_number = payload.get("for_whatsapp", "NOMOR_TIDAK_ADA")
    
    # Ekstraksi status code (lebih robust)
    status_code = 500
    try:
        # Mencari kode angka 3 digit di awal string
        match = re.search(r'^\d{3}', status_field)
        if match:
             status_code = int(match.group(0))
        elif 'Up' in status_field or 'OK' in status_field: 
             status_code = 200
        # Jika status_field kosong (seperti pada log Anda), status_code tetap 500
    except Exception:
        pass # Biarkan status_code tetap 500 jika ada error parsing

    
    # Tentukan Pesan Notifikasi Berdasarkan Status
    if status_code == 200:
        notification_text = f"✅ LAYANAN UP! {description}"
    else:
        notification_text = f"🚨 LAYANAN DOWN ({status_code})! Mohon segera dicek. Detail: {description}"
    
    
    # Kirim Notifikasi ke Go WhatsApp API
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
        "service_status": status_field,
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }

# *Tambahan: Endpoint untuk testing dasar*
@app.get("/")
def read_root():
    return {"message": "Webhook Bridge Aktif di Port 3010"}
