from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: str
    balance: float
    role: str

    class Config:
        from_attributes = True


class NftCollectionBase(BaseModel):
    name: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    contract_address: Optional[str] = None


class NftCollectionCreate(NftCollectionBase):
    pass


class NftCollectionOut(NftCollectionBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class NFTCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    nft_address: Optional[str] = None
    collection_id: Optional[int] = None
    owner_telegram_id: Optional[int] = None


class NFTOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    nft_address: Optional[str] = None
    collection_id: Optional[int] = None
    owner_id: Optional[int] = None
    is_for_sale: bool
    price: Optional[float] = None
    seller_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SellRequest(BaseModel):
    nft_id: int
    price: float
    seller_address: Optional[str] = None


class BuyRequest(BaseModel):
    nft_id: int


class PricePoint(BaseModel):
    price: float
    timestamp: datetime

    class Config:
        from_attributes = True


class ConfirmBuyRequest(BaseModel):
    nft_id: int
    tx_boc: str


class TopUpRequest(BaseModel):
    ton_amount: float


class TopUpConfirmRequest(BaseModel):
    topup_id: int
    tx_boc: str


class TopUpOut(BaseModel):
    id: int
    ton_amount: float
    pink_amount: float
    treasury_address: str
    comment: str
    payload: Optional[str] = None
    status: str

    class Config:
        from_attributes = True
