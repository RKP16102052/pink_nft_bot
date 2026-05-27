import hmac
import hashlib
import time
from urllib.parse import unquote
from config import BOT_TOKEN

def validate_init_data(init_data_str: str) -> dict:
    parsed = {}
    for pair in init_data_str.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            parsed[key] = unquote(value)

    received_hash = parsed.pop("hash", "")
    keys = sorted(parsed.keys())
    data_check_arr = [f"{key}={parsed[key]}" for key in keys]
    data_check_string = "\n".join(data_check_arr)

    secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if hmac_hash != received_hash:
        raise ValueError("Invalid hash")

    auth_date = int(parsed["auth_date"])
    if time.time() - auth_date > 86400:   # 24 часа
        raise ValueError("Init data expired")

    return parsed
