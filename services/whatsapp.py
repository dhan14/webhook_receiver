import httpx
import logging
from typing import Dict, Any

from .config import WA_API_URL, WA_RECONNECT_URL, WA_USERNAME, WA_PASSWORD

async def _perform_wa_request(client: httpx.AsyncClient, url: str, payload: Dict[str, Any], is_reconnect: bool = False):
    auth_tuple = (WA_USERNAME, WA_PASSWORD)
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
            response = await _perform_wa_request(client, WA_API_URL, whatsapp_payload)
            
            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim (Percobaan 1). Status: {response.status_code}")
                return True, response.json()
            
            elif response.status_code == 401:
                logging.warning("⚠️ Otorisasi WA GAGAL (401). Mencoba Reconnect dan Retry...")
                
                # RECONNECT STEP
                reconnect_response = await _perform_wa_request(client, WA_RECONNECT_URL, {}, is_reconnect=True)
                
                if reconnect_response.status_code >= 200 and reconnect_response.status_code < 300:
                    logging.info("✅ Reconnect ke WA API Sukses. Mencoba kirim ulang pesan...")
                    
                    # ATTEMPT 2
                    retry_response = await _perform_wa_request(client, WA_API_URL, whatsapp_payload)
                    
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
            response = await _perform_wa_request(client, WA_API_URL, whatsapp_payload)

            if response.status_code >= 200 and response.status_code < 300:
                logging.info(f"✅ Notifikasi WA berhasil dikirim ke grup (Percobaan 1). Status: {response.status_code}")
                return True, response.json()

            elif response.status_code == 401:
                logging.warning("⚠ Otorisasi WA GAGAL (401). Mencoba Reconnect dan Retry...")

                # RECONNECT STEP
                reconnect_response = await _perform_wa_request(client, WA_RECONNECT_URL, {}, is_reconnect=True)

                if reconnect_response.status_code >= 200 and reconnect_response.status_code < 300:
                    logging.info("✅ Reconnect ke WA API Sukses. Mencoba kirim ulang pesan...")

                    # ATTEMPT 2
                    retry_response = await _perform_wa_request(client, WA_API_URL, whatsapp_payload)

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