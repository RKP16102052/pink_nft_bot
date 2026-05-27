import csv
import io
import json
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from starlette.responses import StreamingResponse

from auth import validate_init_data
from config import ADMIN_IDS, PINK_PER_TON, PINK_TREASURY_ADDRESS, TON_NETWORK_ID
from database import async_session
from models import NFT, NftCollection, PinkTopUp, PriceHistory, User
from schemas import (
    BuyRequest,
    ConfirmBuyRequest,
    NFTCreate,
    NFTOut,
    NftCollectionCreate,
    NftCollectionOut,
    PricePoint,
    SellRequest,
    TopUpConfirmRequest,
    TopUpOut,
    TopUpRequest,
    UserOut,
)
from ton_client import build_text_comment_payload, verify_payment

router = APIRouter(prefix="/api", tags=["api"])


async def get_db():
    async with async_session() as session:
        yield session


def clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


async def get_or_create_user(
    db: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> User:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    role = "admin" if telegram_id in ADMIN_IDS else "user"

    if user:
        if user.telegram_id in ADMIN_IDS and user.role != "admin":
            user.role = "admin"
            await db.commit()
            await db.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name or f"User {telegram_id}",
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    init_data: str = Header(..., alias="X-Telegram-InitData"),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        data = validate_init_data(init_data)
        user_data = data.get("user")
        if user_data and isinstance(user_data, str):
            user_data = json.loads(user_data)
        if not user_data:
            raise ValueError("User data is missing")

        tg_id = int(user_data["id"])
        username = user_data.get("username")
        first_name = user_data.get("first_name", "User")
    except Exception as exc:
        raise HTTPException(status_code=403, detail=f"Invalid init data: {exc}") from exc

    return await get_or_create_user(db, tg_id, username, first_name)


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/nfts", response_model=List[NFTOut])
async def get_nfts(
    for_sale: Optional[bool] = Query(None),
    my: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(NFT).order_by(NFT.created_at.desc())
    if for_sale is not None:
        query = query.where(NFT.is_for_sale == for_sale)
    if my:
        query = query.where(NFT.owner_id == user.id)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/nfts/sell", response_model=NFTOut)
async def sell_nft(
    req: SellRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nft = await db.get(NFT, req.nft_id)
    if not nft:
        raise HTTPException(status_code=404, detail="NFT not found")
    if nft.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your NFT")
    if req.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be positive")

    nft.is_for_sale = True
    nft.price = req.price
    nft.seller_address = clean_optional_text(req.seller_address)
    nft.locked_by = None
    nft.purchase_id = None
    db.add(PriceHistory(nft_id=nft.id, price=req.price))

    await db.commit()
    await db.refresh(nft)
    return nft


@router.post("/nfts/cancel_sell", response_model=NFTOut)
async def cancel_sell(
    nft_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nft = await db.get(NFT, nft_id)
    if not nft:
        raise HTTPException(status_code=404, detail="NFT not found")
    if nft.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your NFT")
    if not nft.is_for_sale:
        raise HTTPException(status_code=400, detail="Not for sale")

    nft.is_for_sale = False
    nft.price = None
    nft.seller_address = None
    nft.locked_by = None
    nft.purchase_id = None

    await db.commit()
    await db.refresh(nft)
    return nft


@router.post("/nfts/buy/internal", response_model=NFTOut)
async def buy_nft_internal(
    req: BuyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nft = await db.get(NFT, req.nft_id)
    if not nft or not nft.is_for_sale or nft.price is None:
        raise HTTPException(status_code=400, detail="NFT not for sale")
    if nft.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own NFT")
    if nft.owner_id is None:
        raise HTTPException(status_code=400, detail="NFT has no seller")
    if user.balance < nft.price:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    seller = await db.get(User, nft.owner_id)
    price = nft.price

    user.balance -= price
    if seller:
        seller.balance += price

    db.add(PriceHistory(nft_id=nft.id, price=price))
    nft.owner_id = user.id
    nft.is_for_sale = False
    nft.price = None
    nft.seller_address = None
    nft.locked_by = None
    nft.purchase_id = None

    await db.commit()
    await db.refresh(nft)
    return nft


@router.post("/nfts/buy/request")
async def request_buy(
    req: BuyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nft = await db.get(NFT, req.nft_id)
    if not nft or not nft.is_for_sale or nft.price is None:
        raise HTTPException(status_code=400, detail="NFT not for sale")
    if nft.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own NFT")
    if not nft.seller_address:
        raise HTTPException(status_code=400, detail="Seller TON address is missing")
    if nft.locked_by is not None:
        raise HTTPException(status_code=400, detail="NFT is already locked for purchase")

    purchase_id = secrets.token_hex(16)
    nft.purchase_id = purchase_id
    nft.locked_by = user.id
    await db.commit()

    return {
        "purchase_id": purchase_id,
        "amount": nft.price,
        "seller_address": nft.seller_address,
        "comment": f"buy_{purchase_id}",
    }


@router.post("/nfts/buy/confirm")
async def confirm_buy(
    req: ConfirmBuyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nft = await db.get(NFT, req.nft_id)
    if not nft:
        raise HTTPException(status_code=404, detail="NFT not found")
    if nft.locked_by != user.id:
        raise HTTPException(status_code=400, detail="Purchase not requested by you")

    is_valid = await verify_payment(
        boc=req.tx_boc,
        expected_amount=nft.price,
        seller_address=nft.seller_address,
        comment=f"buy_{nft.purchase_id}",
    )
    if not is_valid:
        nft.locked_by = None
        nft.purchase_id = None
        await db.commit()
        raise HTTPException(status_code=400, detail="Transaction verification failed")

    db.add(PriceHistory(nft_id=nft.id, price=nft.price))

    nft.owner_id = user.id
    nft.is_for_sale = False
    nft.price = None
    nft.seller_address = None
    nft.locked_by = None
    nft.purchase_id = None

    await db.commit()
    return {"status": "ok"}


@router.get("/nfts/{nft_id}/history", response_model=List[PricePoint])
async def get_history(nft_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.nft_id == nft_id)
        .order_by(PriceHistory.timestamp)
    )
    return result.scalars().all()


@router.get("/wallet/topup/rate")
async def get_topup_rate(user: User = Depends(get_current_user)):
    return {
        "pink_per_ton": PINK_PER_TON,
        "treasury_address_configured": bool(PINK_TREASURY_ADDRESS),
        "ton_network": TON_NETWORK_ID,
    }


@router.post("/wallet/topup/request", response_model=TopUpOut)
async def request_pink_topup(
    req: TopUpRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if req.ton_amount <= 0:
        raise HTTPException(status_code=400, detail="TON amount must be positive")
    if not PINK_TREASURY_ADDRESS:
        raise HTTPException(status_code=500, detail="Treasury TON address is not configured")

    comment = f"pink_topup_{secrets.token_hex(12)}"
    topup = PinkTopUp(
        user_id=user.id,
        ton_amount=req.ton_amount,
        pink_amount=req.ton_amount * PINK_PER_TON,
        treasury_address=PINK_TREASURY_ADDRESS,
        comment=comment,
        status="pending",
    )
    db.add(topup)
    await db.commit()
    await db.refresh(topup)

    return TopUpOut(
        id=topup.id,
        ton_amount=topup.ton_amount,
        pink_amount=topup.pink_amount,
        treasury_address=topup.treasury_address,
        comment=topup.comment,
        payload=build_text_comment_payload(topup.comment),
        status=topup.status,
    )


@router.post("/wallet/topup/confirm", response_model=UserOut)
async def confirm_pink_topup(
    req: TopUpConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topup = await db.get(PinkTopUp, req.topup_id)
    if not topup or topup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Top-up request not found")
    if topup.status != "pending":
        raise HTTPException(status_code=400, detail="Top-up request is already processed")

    is_valid = await verify_payment(
        boc=req.tx_boc,
        expected_amount=topup.ton_amount,
        seller_address=topup.treasury_address,
        comment=topup.comment,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="TON payment verification failed")

    topup.status = "confirmed"
    topup.tx_boc = req.tx_boc
    topup.confirmed_at = func.now()
    user.balance += topup.pink_amount

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/wallet/topup/retry_pending", response_model=UserOut)
async def retry_pending_topups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PinkTopUp)
        .where(PinkTopUp.user_id == user.id)
        .where(PinkTopUp.status == "pending")
        .order_by(PinkTopUp.created_at)
    )
    pending_topups = result.scalars().all()

    for topup in pending_topups:
        is_valid = await verify_payment(
            boc=topup.tx_boc,
            expected_amount=topup.ton_amount,
            seller_address=topup.treasury_address,
            comment=topup.comment,
        )
        if not is_valid:
            continue

        topup.status = "confirmed"
        topup.confirmed_at = func.now()
        user.balance += topup.pink_amount

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/admin/logs")
async def get_logs(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PriceHistory, NFT)
        .join(NFT, PriceHistory.nft_id == NFT.id, isouter=True)
        .order_by(PriceHistory.timestamp)
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "type",
            "id",
            "user_id",
            "nft_id",
            "nft_name",
            "price",
            "ton_amount",
            "pink_amount",
            "status",
            "comment",
            "timestamp",
        ]
    )
    for log, nft in result.all():
        writer.writerow(
            [
                "price",
                log.id,
                "",
                log.nft_id,
                nft.name if nft else "",
                log.price,
                "",
                "",
                "",
                "",
                log.timestamp.isoformat(),
            ]
        )

    topups_result = await db.execute(select(PinkTopUp).order_by(PinkTopUp.created_at))
    for topup in topups_result.scalars().all():
        writer.writerow(
            [
                "topup",
                topup.id,
                topup.user_id,
                "",
                "",
                "",
                topup.ton_amount,
                topup.pink_amount,
                topup.status,
                topup.comment,
                topup.created_at.isoformat(),
            ]
        )

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=price-history.csv"},
    )


@router.post("/admin/collections", response_model=NftCollectionOut)
async def create_collection(
    collection: NftCollectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_admin_user),
):
    data = collection.model_dump()
    data["contract_address"] = clean_optional_text(data.get("contract_address"))
    data["image_url"] = clean_optional_text(data.get("image_url")) or ""

    db_collection = NftCollection(**data, owner_id=user.id)
    db.add(db_collection)
    await db.commit()
    await db.refresh(db_collection)
    return db_collection


@router.get("/collections", response_model=List[NftCollectionOut])
async def get_collections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(NftCollection).order_by(NftCollection.created_at.desc()))
    return result.scalars().all()


@router.post("/admin/nfts", response_model=NFTOut)
async def add_nft(
    nft: NFTCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_admin_user),
):
    data = nft.model_dump()
    owner_telegram_id = data.pop("owner_telegram_id", None)
    owner = user

    if owner_telegram_id:
        owner = await get_or_create_user(db, owner_telegram_id)

    data["image_url"] = clean_optional_text(data.get("image_url")) or ""
    data["nft_address"] = clean_optional_text(data.get("nft_address"))
    data["owner_id"] = owner.id

    db_nft = NFT(**data)
    db.add(db_nft)
    await db.commit()
    await db.refresh(db_nft)
    return db_nft
