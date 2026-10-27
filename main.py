"""大肥鱼直播互动 - FastAPI 入口

启动：
    python main.py

端点：
    POST /webhook/douyin     抖音官方 Webhook 事件回调
    GET  /health             健康检查
    POST /test/comment       测试：手动模拟一条弹幕
    GET  /cards              查看待展示的卡片队列
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
import uvicorn

from app.config import get_env
from app.douyin.official_webhook import parse_webhook
from app.douyin.ws_client import ws_runner
from app.handlers.router import handle_event

# 配置日志
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="INFO")

app = FastAPI(title="大肥鱼直播互动", version="0.1.0")

# 待推送卡片队列（互动插件前端轮询这里拿数据）
_card_queue: deque = deque(maxlen=100)


async def _dispatch(event: dict[str, Any]):
    """事件分发：处理 -> 入队卡片"""
    try:
        card = await handle_event(event)
        if card:
            _card_queue.append(card)
            logger.info(f"生成卡片: {card}")
    except Exception as e:
        logger.exception(f"事件处理异常: {e}")


@app.on_event("startup")
async def _startup():
    env = get_env()
    logger.info(f"大肥鱼直播互动启动 | mode=official_webhook | port={env.port}")
    # 如果配置了 WS 模式，后台启动
    if env.douyin_sign_api_url and env.douyin_live_web_rid:
        ws_runner.on_event(_dispatch)
        asyncio.create_task(ws_runner.start())
        logger.info("WebSocket 弹幕模式已启动")


@app.on_event("shutdown")
async def _shutdown():
    await ws_runner.stop()


# ---------- 路由 ----------

@app.get("/health")
async def health():
    return {"status": "ok", "cards_pending": len(_card_queue)}


@app.post("/webhook/douyin")
async def douyin_webhook(request: Request):
    """抖音官方 Webhook 回调地址"""
    event = await parse_webhook(request)
    asyncio.create_task(_dispatch(event))
    return JSONResponse({"code": 0, "message": "ok"})


@app.get("/cards")
async def pull_cards():
    """互动插件前端轮询：拉取待展示的 AI 回复卡片"""
    cards = []
    while _card_queue:
        cards.append(_card_queue.popleft())
    return {"cards": cards}


@app.post("/test/comment")
async def test_comment(body: dict[str, Any]):
    """测试：手动模拟一条弹幕"""
    event = {
        "source": "test",
        "event_type": body.get("type", "comment"),
        "user_id": body.get("user_id", "test_user_1"),
        "nickname": body.get("nickname", "测试观众"),
        "content": body.get("content", "主播今天吃什么？"),
        "gift_name": body.get("gift_name", ""),
        "gift_count": body.get("gift_count", 0),
    }
    card = await handle_event(event)
    return {"processed": True, "card": card}


if __name__ == "__main__":
    env = get_env()
    uvicorn.run(app, host=env.host, port=env.port, log_level=env.log_level.lower())
