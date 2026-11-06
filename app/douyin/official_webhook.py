"""抖音开放平台 - 直播小玩法数据推送（官方 Webhook）

协议（来自官方文档）：
- Method: POST，content-type: application/json
- Header:
    x-nonce-str   随机字符串
    x-timestamp   毫秒级时间戳
    x-signature   签名（见下方算法）
    x-roomid      房间id
    x-msg-type    live_comment / live_gift / live_like / 其他
- body: 具体消息 payload 的 JSON 序列化字符串（**数组**）

签名算法：
1. 取 header 里除 x-signature、content-type 外的业务字段
   (x-nonce-str, x-timestamp, x-roomid, x-msg-type)
2. 按 key 字典序排序，拼成 key1=value1&key2=value2
3. 直接拼接 body 字符串 + secret（后台配置里填的推送密钥）
4. md5(rawData) 取 16 字节，再 base64 编码 → 得到 signature

不同数据类型在后台配置了不同的推送密钥，按 x-msg-type 选对应密钥验签。
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from fastapi import Request, HTTPException
from loguru import logger

from app.config import get_env


def _secret_for(msg_type: str) -> str:
    """根据消息类型选对应的验签密钥（与抖音后台配置一一对应）"""
    env = get_env()
    mapping = {
        "live_gift": env.douyin_secret_gift,
        "live_comment": env.douyin_secret_comment,
        "live_like": env.douyin_secret_like,
        # 进出房 / 关注事件 msg-type 名称以后台实际为准
        "live_enter": env.douyin_secret_enter,
        "live_follow": env.douyin_secret_follow,
    }
    # 兜底：用通用密钥
    return mapping.get(msg_type, env.douyin_webhook_verify_token)


def verify_signature(headers: dict[str, str], body: bytes, secret: str) -> bool:
    """按官方算法验签"""
    if not secret:
        logger.warning("未配置对应推送密钥，跳过验签")
        return True
    # 1. 收集业务字段（排除 x-signature / content-type）
    fields: dict[str, str] = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in ("x-signature", "content-type", "content_length"):
            continue
        if kl.startswith("x-"):
            fields[kl] = v

    # 2. 按 key 字典序排序拼接
    kv_list = [f"{k}={fields[k]}" for k in sorted(fields.keys())]
    url_params = "&".join(kv_list)

    # 3. 拼接 body + secret（UTF-8）
    raw_data = url_params + body.decode("utf-8", errors="ignore") + secret

    # 4. md5 -> base64
    md5_bytes = hashlib.md5(raw_data.encode("utf-8")).digest()
    expected = base64.b64encode(md5_bytes).decode("utf-8")

    received = headers.get("x-signature", "")
    if expected != received:
        logger.warning(
            f"验签失败: expected={expected} received={received} "
            f"raw={raw_data[:120]}"
        )
        return False
    return True


async def parse_webhook(request: Request) -> list[dict[str, Any]]:
    """解析抖音推送，返回标准化事件列表（payload 是数组）"""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    msg_type = headers.get("x-msg-type", "unknown")
    room_id = headers.get("x-roomid", "")

    # 按 msg-type 选密钥验签
    secret = _secret_for(msg_type)
    if not verify_signature(headers, body, secret):
        raise HTTPException(status_code=403, detail="signature mismatch")

    # 解析 payload（数组）
    try:
        raw_payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")

    if not isinstance(raw_payload, list):
        raw_payload = [raw_payload]

    # payload 内每个元素转成统一事件结构
    events: list[dict[str, Any]] = []
    for item in raw_payload:
        if not isinstance(item, dict):
            continue
        # 礼物测试数据过滤
        if item.get("test") is True:
            logger.info(f"过滤测试数据: {item.get('nickname')}")
            continue

        events.append({
            "source": "douyin_webhook",
            "msg_type": msg_type,
            "room_id": room_id,
            "msg_id": item.get("msg_id", ""),
            "user_id": item.get("sec_openid", ""),
            "nickname": item.get("nickname", "观众"),
            "content": item.get("content", ""),
            "gift_id": item.get("sec_gift_id", ""),
            "gift_count": int(item.get("gift_num") or 0),
            "gift_value": int(item.get("gift_value") or 0),  # 单位：分
            "like_num": int(item.get("like_num") or 0),
            "avatar_url": item.get("avatar_url", ""),
            "timestamp": int(item.get("timestamp") or 0),
        })

    logger.info(f"收到抖音事件: type={msg_type} room={room_id} count={len(events)}")
    return events
