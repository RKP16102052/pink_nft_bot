from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String)
    balance = Column(Float, default=1000.0)
    role = Column(String, default="user")  # user / admin

    collections = relationship("NftCollection", back_populates="owner")
    nfts = relationship("NFT", back_populates="owner")


class NftCollection(Base):
    __tablename__ = "nft_collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    image_url = Column(String, default="")                # Обложка коллекции
    contract_address = Column(String, unique=True, nullable=True)  # Адрес контракта коллекции в TON
    owner_id = Column(Integer, ForeignKey("users.id"))    # Кто создал коллекцию
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="collections")
    nfts = relationship("NFT", back_populates="collection")


class NFT(Base):
    __tablename__ = "nfts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    image_url = Column(String, default="")

    nft_address = Column(String, unique=True, nullable=True)    # Адрес смарт-контракта конкретного NFT
    collection_id = Column(Integer, ForeignKey("nft_collections.id"), nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_for_sale = Column(Boolean, default=False)
    price = Column(Float, nullable=True)                     # Цена в TON
    seller_address = Column(String, nullable=True)           # Адрес продавца
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Поля, необходимые для блокчейн-покупки
    purchase_id = Column(String, nullable=True)
    locked_by = Column(Integer, nullable=True)

    owner = relationship("User", back_populates="nfts")
    collection = relationship("NftCollection", back_populates="nfts")
    price_history = relationship("PriceHistory", back_populates="nft", cascade="all, delete-orphan")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    nft_id = Column(Integer, ForeignKey("nfts.id"))
    price = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    nft = relationship("NFT", back_populates="price_history")


class PinkTopUp(Base):
    __tablename__ = "pink_topups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ton_amount = Column(Float, nullable=False)
    pink_amount = Column(Float, nullable=False)
    treasury_address = Column(String, nullable=False)
    comment = Column(String, unique=True, nullable=False)
    status = Column(String, default="pending")
    tx_boc = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
