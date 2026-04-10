"""Telegram delivery – push notification for the daily digest."""

from __future__ import annotations

import logging

from telegram import Bot

from overpass.config import load_config

logger = logging.getLogger("overpass.delivery.telegram")


async def send_digest_notification(summary_line: str, briefing_url: str) -> None:
    """Send the daily digest push notification to the configured Telegram chat.

    The message contains the one-line summary and a link to the full briefing.
    Silently skips if bot token or chat ID are not configured.
    """
    config = load_config()
    tg = config.telegram
    bot_token = tg.bot_token_env
    chat_id = tg.chat_id_env

    if not bot_token:
        logger.warning("Telegram bot token not configured – skipping notification")
        return
    if not chat_id:
        logger.warning("Telegram chat ID not configured – skipping notification")
        return

    text = f"{summary_line}\n\n{briefing_url}"

    async with Bot(token=bot_token) as bot:
        await bot.send_message(chat_id=chat_id, text=text)

    logger.info("Telegram notification sent to chat %s", chat_id)
