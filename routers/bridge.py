from fastapi import APIRouter, Request
# Import parser dari folder services
from services.parser import sanitize_and_parse_payload, determine_status_and_text
from services.whatsapp import send_whatsapp_notification_phone, send_whatsapp_notification_group
import logging

router = APIRouter()

@router.post("/webhook/uptime-kuma/phone", response_model=None) 
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

@router.post("/webhook/uptime-kuma/group", response_model=None)
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