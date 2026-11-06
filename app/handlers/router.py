"""业务处理器：把原始事件路由到 AI 生成 + 输出"""
from __future__ import annotations

import random
import time
from typing import Any

from loguru import logger

from app.ai.deepseek import ai, limiter
from app.config import get_env, get_persona
from app.output.card_renderer import render_welcome_card, render_reply_card


# 进房去重：同一用户 N 秒内只欢迎一次
_welcomed_users: dict[str, float] = {}
# msg_id 去重：抖音可能重复推送
_seen_msg_ids: dict[str, float] = {}


async def handle_event(event: dict[str, Any]) -> dict | None:
    """主事件入口，返回要输出的卡片数据"""
    msg_type = event.get("msg_type", "")
    user_id = event.get("user_id") or event.get("nickname", "")
    nickname = event.get("nickname", "观众")
    msg_id = event.get("msg_id", "")

    # msg_id 去重（保留 1 小时窗口）
    now = time.time()
    if msg_id:
        last = _seen_msg_ids.get(msg_id, 0)
        if now - last < 3600:
            logger.debug(f"重复消息跳过: {msg_id}")
            return None
        _seen_msg_ids[msg_id] = now

    env = get_env()
    persona_cfg = get_persona()
    welcome_cfg = persona_cfg.get("welcome", {})
    chat_cfg = persona_cfg.get("chat_reply", {})

    # 限流
    if not limiter.allow(user_id, env.rate_limit_per_user_sec, env.rate_limit_global_per_min):
        logger.debug(f"限流跳过: {nickname}")
        return None

    # ---- 评论（弹幕）----
    if msg_type == "live_comment":
        if not chat_cfg.get("enabled", True):
            return None
        content = event.get("content", "")
        if not content:
            return None
        blocked = chat_cfg.get("block_keywords", [])
        if any(b in content for b in blocked):
            return None
        triggers = chat_cfg.get("trigger_keywords", [])
        if triggers and not any(t in content for t in triggers):
            return None

        text = await ai.reply_comment(user_id, nickname, content)
        if not text:
            return None
        logger.info(f"[弹幕回复] {nickname}: {content} -> {text}")
        return render_reply_card(nickname, content, text)

    # ---- 礼物 ----
    if msg_type == "live_gift":
        gift_cfg = chat_cfg.get("on_gift", {})
        if not gift_cfg.get("enabled", True):
            return None
        count = event.get("gift_count", 0)
        value = event.get("gift_value", 0)  # 单位：分
        if count < gift_cfg.get("min_value", 1):
            return None
        text = await ai.thank_gift(nickname, "礼物", count)
        if text:
            logger.info(f"[礼物感谢] {nickname} 送礼物x{count} (价值{value}分): {text}")
            return render_reply_card(nickname, f"送了礼物x{count}", text)

    # ---- 点赞（轻量处理，不打扰）----
    if msg_type == "live_like":
        like_num = event.get("like_num", 0)
        logger.debug(f"[点赞] {nickname} x{like_num}")
        return None

    # ---- 进房欢迎（若平台推送了进房事件）----
    if msg_type in ("live_enter", "user_enter", "enter"):
        if not welcome_cfg.get("trigger_on_enter", True):
            return None
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
        logger.info(f"[进房欢迎] {nickname}: {text}")
        return render_welcome_card(nickname, text)

    # ---- 关注事件 ----
    if msg_type in ("live_follow", "follow"):
        if chat_cfg.get("on_follow", {}).get("enabled", True):
            text = f"谢谢 {nickname} 的关注！🐟"
            return render_reply_card(nickname, "关注了主播", text)

    return None
