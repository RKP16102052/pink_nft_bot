import os

BOT_TOKEN = "API-BOT-TOKEN"
ADMIN_IDS = [2050418885]
DATABASE_URL = "sqlite+aiosqlite:///./nft_bot.db"
WEBAPP_URL = "YOUR-WEB-URL"
PINK_PER_TON = float(os.getenv("PINK_PER_TON", "100"))
PINK_TREASURY_ADDRESS = os.getenv("PINK_TREASURY_ADDRESS", "0QCP28sByTvC0BmeocWsivaovvPuhzW98hnYCqT0mzcoJL8b")

# Testnet settings
TON_NETWORK_ID = os.getenv("TON_NETWORK_ID", "-3")
TONCENTER_API_BASE = os.getenv("TONCENTER_API_BASE", "https://testnet.toncenter.com/api/v2")
