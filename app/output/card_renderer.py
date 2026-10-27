"""输出层：把 AI 回复渲染成互动插件卡片格式

官方互动插件通过 tt.updateCardData 把数据推到直播间卡片上展示。
这里只生成标准化的卡片 dict，前端插件（小程序）负责渲染。
"""
from __future__ import annotations

from typing import Any


def render_welcome_card(nickname: str, text: str) -> dict[str, Any]:
    return {
        "card_type": "welcome",
        "title": "🎉 新观众来了",
        "nickname": nickname,
        "text": text,
        "display_sec": 5,
    }


def render_reply_card(nickname: str, user_msg: str, ai_reply: str) -> dict[str, Any]:
    return {
        "card_type": "reply",
        "title": "💬 AI 互动",
        "nickname": nickname,
        "user_msg": user_msg,
        "ai_reply": ai_reply,
        "display_sec": 5,
    }


def render_to_websocket_output(card: dict) -> str:
    """如果走 WS 模式，把卡片转成要发送的弹幕文本（占位，实际发送通道自行对接）"""
    if card["card_type"] == "welcome":
        return card["text"]
    if card["card_type"] == "reply":
        return f"@{card['nickname']} {card['ai_reply']}"
    return ""
