import csv
import io
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from config import ADMIN_IDS, BOT_TOKEN, WEBAPP_URL
from database import Base, async_session, engine
from models import NFT, PinkTopUp, PriceHistory, User

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def is_admin(message: types.Message) -> bool:
    return bool(message.from_user and message.from_user.id in ADMIN_IDS)


async def get_or_create_bot_user(session, telegram_user: types.User) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_user.id))
    user = result.scalar_one_or_none()
    if user:
        if telegram_user.id in ADMIN_IDS and user.role != "admin":
            user.role = "admin"
            await session.commit()
            await session.refresh(user)
        return user

    user = User(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name or "User",
        role="admin" if telegram_user.id in ADMIN_IDS else "user",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@dp.message(Command("start"))
async def start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Открыть Pink NFT",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/webapp"),
    )
    await message.answer(
        "Pink NFT готов к работе. Откройте мини-приложение, чтобы смотреть рынок, графики и свои NFT.",
        reply_markup=kb.as_markup(),
    )


@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа к админке.")
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="Открыть админку",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/webapp?mode=admin"),
    )
    await message.answer(
        "Админ-команды:\n"
        "/logs - выгрузить CSV логов\n"
        "/add_nft Название | Описание | URL картинки | Адрес NFT | Telegram ID владельца",
        reply_markup=kb.as_markup(),
    )


@dp.message(Command("logs"))
async def logs_cmd(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа к логам.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(PriceHistory, NFT)
            .join(NFT, PriceHistory.nft_id == NFT.id, isouter=True)
            .order_by(PriceHistory.timestamp)
        )
        rows = result.all()
        topups_result = await session.execute(select(PinkTopUp).order_by(PinkTopUp.created_at))
        topups = topups_result.scalars().all()

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
    for log, nft in rows:
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
    for topup in topups:
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

    file = BufferedInputFile(
        output.getvalue().encode("utf-8-sig"),
        filename="price-history.csv",
    )
    await message.answer_document(file, caption="Логи цен выгружены.")


@dp.message(Command("add_nft"))
async def add_nft_cmd(message: types.Message, command: CommandObject):
    if not is_admin(message):
        await message.answer("Нет доступа к добавлению NFT.")
        return
    if not command.args:
        await message.answer(
            "Формат:\n"
            "/add_nft Название | Описание | URL картинки | Адрес NFT | Telegram ID владельца"
        )
        return

    parts = [part.strip() for part in command.args.split("|")]
    if not parts[0]:
        await message.answer("Название NFT обязательно.")
        return

    name = parts[0]
    description = parts[1] if len(parts) > 1 else ""
    image_url = parts[2] if len(parts) > 2 else ""
    nft_address = parts[3] if len(parts) > 3 and parts[3] else None
    owner_telegram_id = message.from_user.id

    if len(parts) > 4 and parts[4]:
        try:
            owner_telegram_id = int(parts[4])
        except ValueError:
            await message.answer("Telegram ID владельца должен быть числом.")
            return

    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == owner_telegram_id))
            owner = result.scalar_one_or_none()
            if not owner:
                owner = User(
                    telegram_id=owner_telegram_id,
                    first_name=f"User {owner_telegram_id}",
                    role="admin" if owner_telegram_id in ADMIN_IDS else "user",
                )
                session.add(owner)
                await session.flush()

            nft = NFT(
                name=name,
                description=description,
                image_url=image_url,
                nft_address=nft_address,
                owner_id=owner.id,
            )
            session.add(nft)
            await session.commit()
            await session.refresh(nft)
    except SQLAlchemyError as exc:
        logging.exception("Failed to add NFT from bot")
        await message.answer(f"Не удалось добавить NFT: {exc.__class__.__name__}")
        return

    await message.answer(f"NFT #{nft.id} добавлен: {nft.name}")


async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables created")
