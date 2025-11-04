# main.py
from fastapi import FastAPI
from typing import Dict, Any
import json
import logging
import httpx 
from dotenv import load_dotenv # Import untuk memuat .env
import os 

# 1. Muat .env di awal
load_dotenv() 

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(
    title="Webhook Bridge FastAPI",
    description="Meneruskan notifikasi Uptime Kuma ke layanan Go WhatsApp",
    version="1.0.0"
)

# 2. Ambil nilai dari .env menggunakan os.getenv()
WHATSAPP_API_URL = os.getenv("WA_API_URL", "http://localhost:3000/send/message")
WHATSAPP_USERNAME = os.getenv("WA_USER", "default_user") 
WHATSAPP_PASSWORD = os.getenv("WA_PASS", "default_pass")
# -----------------------------------

class WebhookResponse(Dict[str, Any]):
    message: str

async def send_whatsapp_notification(phone_number: str, text_message: str):
    """Mengirim pesan notifikasi ke endpoint Go WhatsApp."""
    
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


@app.post("/webhook/uptime-kuma", response_model=WebhookResponse)
async def handle_uptime_kuma_webhook(payload: Dict[str, Any]):
    """Menerima payload webhook, memproses status, dan meneruskan ke Go WhatsApp."""
    
    logging.info("--- Payload Webhook Diterima ---")
    print(json.dumps(payload, indent=4))
    
    status_field = payload.get("status", "")
    description = payload.get("description", "Detail tidak tersedia.")
    target_whatsapp_number = payload.get("for_whatsapp", "NOMOR_TIDAK_ADA")
    
    # Ekstraksi kode status
    try:
        status_code = int(status_field.split(' ')[0])
    except:
        status_code = 500
        
    
    # Tentukan Pesan Notifikasi Berdasarkan Status
    if status_code == 200:
        notification_text = f"✅ LAYANAN UP! {description}"
    else:
        notification_text = f"🚨 LAYANAN DOWN ({status_code})! Mohon segera dicek. Detail: {description}"
    
    
    # Kirim Notifikasi ke Go WhatsApp API (hanya jika nomor tersedia)
    wa_success = False
    wa_result = {}
    
    if target_whatsapp_number != "NOMOR_TIDAK_ADA":
        wa_success, wa_result = await send_whatsapp_notification(
            phone_number=target_whatsapp_number, 
            text_message=notification_text
        )
    else:
        logging.warning("Nomor WhatsApp tidak ditemukan di payload ('for_whatsapp'). Notifikasi WA dilewatkan.")


    # Buat Respons Akhir untuk Uptime Kuma
    if wa_success:
        response_message = f"Webhook DITERIMA & Notifikasi WA Sukses dikirim. Status Layanan: {status_field}"
    else:
        response_message = f"Webhook DITERIMA. Notifikasi WA GAGAL dikirim. Status Layanan: {status_field}"

    return {
        "message": response_message,
        "service_status": status_field,
        "wa_sent": wa_success,
        "wa_api_result": wa_result
    }
