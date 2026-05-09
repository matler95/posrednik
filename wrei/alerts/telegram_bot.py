import os

import requests


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_alert(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise EnvironmentError("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID w zmiennych środowiskowych.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    response = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    response.raise_for_status()
