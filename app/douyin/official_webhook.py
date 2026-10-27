"""抖音开放平台 - 官方 Webhook 事件接收

对应直播小玩法「数据推送任务」：
- 平台把评论/礼物/点赞/进房等事件 POST 到你配置的回调地址
- 你在控制台配置 Webhook URL，平台推数据过来
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Request, HTTPException
from loguru import logger

from app.config import get_env


def verify_signature(timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
    """抖音 Webhook 验签（示例实现，按官方文档调整）"""
    token = get_env().douyin_webhook_verify_token
    if not token:
        logger.warning("未配置 DOUYIN_WEBHOOK_VERIFY_TOKEN，跳过验签")
        return True
    # 官方验签逻辑：按字典序拼接 token + timestamp + nonce + body 后 sha256
    payload = "".join(sorted([token, timestamp, nonce, body.decode("utf-8", errors="ignore")]))
    expected = hashlib.sha256(payload.encode()).hexdigest()
    return expected == signature


async def parse_webhook(request: Request) -> dict[str, Any]:
    """解析抖音推送的事件，返回标准化事件字典"""
    body = await request.body()
    headers = request.headers

    # 验签
    ts = headers.get("x-douyin-timestamp", "")
    nonce = headers.get("x-douyin-nonce", "")
    sign = headers.get("x-douyin-signature", "")
    if sign and not verify_signature(ts, nonce, body, sign):
        raise HTTPException(status_code=403, detail="signature mismatch")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")

    logger.debug(f"收到抖音事件: {json.dumps(data, ensure_ascii=False)[:300]}")

    # 把官方 payload 标准化成内部事件结构
    event_type = data.get("event_type") or data.get("type") or "unknown"
    payload = data.get("payload", data)

    return {
        "source": "official_webhook",
        "event_type": event_type,   # comment / gift / like / enter / follow
        "raw": data,
        "user_id": str(payload.get("user_id") or payload.get("open_id") or ""),
        "nickname": payload.get("nickname") or payload.get("user_name") or "神秘观众",
        "content": payload.get("content") or payload.get("comment") or "",
        "gift_name": payload.get("gift_name") or "",
        "gift_count": int(payload.get("gift_count") or payload.get("count") or 0),
    }
