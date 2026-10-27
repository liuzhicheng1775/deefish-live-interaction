"""业务处理器：把原始事件路由到 AI 生成 + 输出"""
from __future__ import annotations

import random
from typing import Any

from loguru import logger

from app.ai.deepseek import ai, limiter
from app.config import get_env, get_persona
from app.output.card_renderer import render_welcome_card, render_reply_card


# 进房去重：同一用户 5 分钟内只欢迎一次
_welcomed_users: dict[str, float] = {}


async def handle_event(event: dict[str, Any]) -> dict | None:
    """主事件入口，返回要输出的卡片数据"""
    etype = event.get("event_type", "")
    user_id = event.get("user_id") or event.get("nickname", "")
    nickname = event.get("nickname", "观众")

    env = get_env()
    persona_cfg = get_persona()
    welcome_cfg = persona_cfg.get("welcome", {})
    chat_cfg = persona_cfg.get("chat_reply", {})

    # 限流
    if not limiter.allow(user_id, env.rate_limit_per_user_sec, env.rate_limit_global_per_min):
        logger.debug(f"限流跳过: {nickname}")
        return None

    # ---- 进房欢迎 ----
    if etype in ("enter", "user_enter", "welcome"):
        if not welcome_cfg.get("trigger_on_enter", True):
            return None
        import time
        now = time.time()
        dedup = welcome_cfg.get("dedup_window_sec", 300)
        if now - _welcomed_users.get(user_id, 0) < dedup:
            return None
        _welcomed_users[user_id] = now

        if welcome_cfg.get("use_ai", True):
            text = await ai.welcome(nickname)
        else:
            tpl = random.choice(welcome_cfg.get("templates", ["欢迎{nickname}！"]))
            emoji = random.choice(welcome_cfg.get("emojis", ["🐟"]))
            text = tpl.format(nickname=nickname, emoji=emoji)

        logger.info(f"[欢迎] {nickname}: {text}")
        return render_welcome_card(nickname, text)

    # ---- 弹幕回复 ----
    if etype in ("comment", "chat", "danmaku", "barrage"):
        if not chat_cfg.get("enabled", True):
            return None
        content = event.get("content", "")
        if not content:
            return None
        # 黑名单
        blocked = chat_cfg.get("block_keywords", [])
        if any(b in content for b in blocked):
            return None
        # 关键词触发（留空则全回）
        triggers = chat_cfg.get("trigger_keywords", [])
        if triggers and not any(t in content for t in triggers):
            return None

        text = await ai.reply_comment(user_id, nickname, content)
        if not text:
            return None
        logger.info(f"[回复] {nickname}: {content} -> {text}")
        return render_reply_card(nickname, content, text)

    # ---- 礼物感谢 ----
    if etype in ("gift", "gift_send"):
        gift_cfg = chat_cfg.get("on_gift", {})
        if not gift_cfg.get("enabled", True):
            return None
        gift_name = event.get("gift_name", "礼物")
        count = event.get("gift_count", 1)
        if count < gift_cfg.get("min_value", 1):
            return None
        text = await ai.thank_gift(nickname, gift_name, count)
        if text:
            logger.info(f"[感谢] {nickname} 送 {gift_name}x{count}: {text}")
            return render_reply_card(nickname, f"送了{gift_name}x{count}", text)

    # ---- 关注感谢 ----
    if etype in ("follow", "user_follow"):
        if chat_cfg.get("on_follow", {}).get("enabled", True):
            text = f"谢谢 {nickname} 的关注！🐟"
            return render_reply_card(nickname, "关注了主播", text)

    return None
