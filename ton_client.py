import base64
from decimal import Decimal
from typing import Any

import aiohttp
from tonsdk.boc import Cell
from tonsdk.utils import Address, InvalidAddressError

from config import TONCENTER_API_BASE


def build_text_comment_payload(comment: str) -> str:
    cell = Cell()
    cell.bits.write_uint(0, 32)
    cell.bits.write_string(comment)
    return base64.b64encode(cell.to_boc(False)).decode()


def to_nanotons(amount: float) -> int:
    return int(Decimal(str(amount)) * Decimal("1000000000"))


def normalize_address(address: str | None) -> str:
    if not address:
        return ""
    try:
        return Address(address).to_string(is_user_friendly=False)
    except (InvalidAddressError, ValueError):
        return address.strip()


def values_equal_address(left: str | None, right: str | None) -> bool:
    return bool(left and right and normalize_address(left) == normalize_address(right))


def value_contains_comment(value: Any, comment: str) -> bool:
    if value is None:
        return False

    text = str(value)
    if comment in text:
        return True

    try:
        decoded = base64.b64decode(text + "===")
        return comment.encode() in decoded
    except Exception:
        return False


def message_contains_comment(message: dict[str, Any], comment: str) -> bool:
    candidates: list[Any] = [
        message.get("message"),
        message.get("comment"),
        message.get("body"),
    ]

    msg_data = message.get("msg_data")
    if isinstance(msg_data, dict):
        candidates.extend(
            [
                msg_data.get("text"),
                msg_data.get("body"),
            ]
        )

    decoded_body = message.get("decoded_body")
    if isinstance(decoded_body, dict):
        candidates.extend(
            [
                decoded_body.get("text"),
                decoded_body.get("comment"),
                decoded_body.get("message"),
            ]
        )

    return any(value_contains_comment(candidate, comment) for candidate in candidates)


def message_matches_payment(
    message: dict[str, Any],
    expected_amount: float,
    recipient_address: str,
    comment: str,
) -> bool:
    if not values_equal_address(message.get("destination"), recipient_address):
        return False

    try:
        value = int(message.get("value", 0))
    except (TypeError, ValueError):
        return False

    if value != to_nanotons(expected_amount):
        return False

    return message_contains_comment(message, comment)


async def verify_payment(
    boc: str | None,
    expected_amount: float,
    seller_address: str,
    comment: str,
    limit: int = 30,
) -> bool:
    """
    Checks the recipient account history for a TON transfer with the expected
    amount and unique text comment. TonConnect returns a wallet message BOC,
    not a reliable recipient transaction hash, so account-history matching is
    the safer verification point for this MVP.
    """
    url = f"{TONCENTER_API_BASE}/getTransactions"
    params = {"address": seller_address, "limit": limit}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return False

                data = await resp.json()
                if not data.get("ok") or not data.get("result"):
                    return False

                for tx in data["result"]:
                    in_msg = tx.get("in_msg") or {}
                    if message_matches_payment(in_msg, expected_amount, seller_address, comment):
                        return True

                return False
        except Exception as exc:
            print(f"Verification error: {exc}")
            return False
