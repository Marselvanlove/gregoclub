import logging
from aiogram import F, Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from database.requests import add_unauthorized_member, get_user_by_telegram_id, remove_unauthorized_member
from utils.config import Config

logger = logging.getLogger(__name__)

router = Router(name="chat_member")


@router.chat_member(F.chat.type == "channel")
async def on_channel_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
    config: Config,
) -> None:
    """
    Обработчик изменений статуса участников канала.
    Отслеживает присоединения к каналу и добавляет неавторизованных пользователей
    в таблицу unauthorized_members для последующего кика через 15 минут.
    """
    # Проверяем, что это именно наш канал подписки
    if event.chat.id != config.channel_id:
        return
    
    # Получаем информацию о пользователе
    user = event.new_chat_member.user
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status
    
    # Игнорируем ботов
    if user.is_bot:
        return
    
    # Проверяем, что пользователь присоединился (статус изменился на member/administrator)
    joined = (
        old_status in ("left", "kicked") 
        and new_status in ("member", "administrator", "creator")
    )
    
    if not joined:
        return
    
    telegram_id = user.id
    full_name = user.full_name
    username = user.username
    
    logger.info(f"Пользователь {telegram_id} (@{username}) присоединился к каналу")
    
    # Проверяем, есть ли пользователь в БД
    db_user = await get_user_by_telegram_id(session, telegram_id)
    
    if db_user is None:
        # Пользователя нет в БД - добавляем в список неавторизованных
        await add_unauthorized_member(
            session=session,
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
        )
        logger.warning(
            f"Неавторизованный пользователь {telegram_id} (@{username}) добавлен в список для кика"
        )
    else:
        # Пользователь есть в БД - удаляем из неавторизованных (если был там)
        await remove_unauthorized_member(session, telegram_id)
        logger.info(
            f"Авторизованный пользователь {telegram_id} (@{username}, статус: {db_user.status.value})"
        )
