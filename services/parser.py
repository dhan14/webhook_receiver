import json
import logging
import re
from typing import Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

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