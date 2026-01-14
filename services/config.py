import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

WA_API_URL= os.getenv("WA_API_URL", "http://localhost:3031/send/message")
WA_RECONNECT_URL = os.getenv("WA_RECONNECT_URL", "http://localhost:3031/app/reconnect")
WA_USERNAME = os.getenv("WA_USER", "default_user") 
WA_PASSWORD = os.getenv("WA_PASS", "default_pass")

PROJECT_NAME = "Webhook Bridge"
VERSION = "1.0.1"