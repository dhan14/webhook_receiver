# main.py
from fastapi import FastAPI
from typing import Dict, Any
import json
import logging
import httpx 
from dotenv import load_dotenv
import os 
# TIDAK PERLU lagi mengimpor BaseModel dari pydantic!

# 1. Muat .env di awal
load_dotenv() 

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# Class WebhookResponse dihapus!

async def send_whatsapp_notification(phone_number: str, text_message: str):
    # ... (fungsi ini tidak berubah) ...
    whatsapp_payload = {
        "phone": f"{phone_number}@s.whatsapp.net",
        "message": text_message,
        "is_forwarded": False
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                WHATSAPP_API_URL,
                json=whatsapp_payload,
                auth=(WHATSAPP_USERNAME, WHATSAPP_PASSWORD) 
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim. Status: {response.status_code}")
                return True, response.json()
            else:
                logging.error(f"❌ Gagal kirim notifikasi WA. Status: {response.status_code}, Body: {response.text}")
                return False, {"error": "Failed to send WA message", "detail": response.text}
                
    except httpx.RequestError as e:
        logging.critical(f"❌ Error koneksi ke Go WhatsApp API: {e}")
        return False, {"error": "Connection error to WA API"}


# Endpoint Webhook Utama
# 🔑 PERHATIKAN: response_model=None ditambahkan di sini
@app.post("/webhook/uptime-kuma", response_model=None) 
async def handle_uptime_kuma_webhook(payload: Dict[str, Any]):
    """Menerima payload webhook, memproses status, dan meneruskan ke Go WhatsApp."""
    
    logging.info("--- Payload Webhook Diterima ---")
    print(json.dumps(payload, indent=4))
    
    status_field = payload.get("status", "")
    description = payload.get("description", "Detail tidak tersedia.")
    target_whatsapp_number = payload.get("for_whatsapp", "NOMOR_TIDAK_ADA")
    
    try:
        status_code = int(status_field.split(' ')[0])
    except:
        status_code = 500
        
    
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


    # Mengembalikan dict Python biasa
    return {
        "message": "Webhook DITERIMA, cek wa_sent untuk status notifikasi WA.",
        "service_status": status_field,
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }
