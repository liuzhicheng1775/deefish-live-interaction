"""抖音直播间 WebSocket 弹幕接入（逆向模式，参考 DouyinLiveJava）

工作流程：
1. 调用签名服务拿到 wssUrl + headers
2. 连接 wss://webcast.../im/push/v2/
3. 心跳保活（10s）
4. 接收 gzip 压缩的 protobuf 消息，解析出弹幕/礼物/进房事件

注意：此模式非官方，有账号风险，仅用于个人研究测试。
生产请用 official_webhook.py。
"""
from __future__ import annotations

import asyncio
import gzip
import json
import struct
from typing import Any, Awaitable, Callable

import httpx
import websockets
from loguru import logger

from app.config import get_env


# 事件处理器类型
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class DouyinWSRunner:
    def __init__(self):
        env = get_env()
        self.sign_api = env.douyin_sign_api_url
        self.cookie = env.douyin_cookie
        self.web_rid = env.douyin_live_web_rid
        self.handlers: list[EventHandler] = []
        self._ws = None
        self._heartbeat_task = None
        self._running = False

    def on_event(self, handler: EventHandler):
        self.handlers.append(handler)

    async def _get_sign(self) -> dict:
        """从签名服务拿 wssUrl"""
        if not self.sign_api:
            raise RuntimeError("未配置 DOUYIN_SIGN_API_URL")
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                f"{self.sign_api}/sign",
                json={"liveId": self.web_rid, "cookie": self.cookie},
            )
            resp.raise_for_status()
            return resp.json()

    async def _heartbeat(self, ws, interval_ms: int = 10000):
        """心跳：发送 0x3a026862 (hb)"""
        payload = bytes.fromhex("3a026862")
        while self._running:
            try:
                await asyncio.sleep(interval_ms / 1000)
                await ws.send(payload)
            except Exception as e:
                logger.warning(f"心跳发送失败: {e}")
                break

    def _parse_frame(self, data: bytes) -> dict | None:
        """解析抖音 webcast 推送帧（简化版，实际需完整 protobuf 定义）

        帧结构：4字节包头 + gzip压缩的protobuf body
        这里只做最小可运行解析，完整 protobuf 定义参考 DouyinLiveJava/client/src/main/proto/douyin.proto
        """
        try:
            # 尝试 gzip 解压
            try:
                raw = gzip.decompress(data)
            except Exception:
                raw = data

            # 简化：从二进制里模糊提取文本字段（实际生产应链接 protobuf）
            # 这里只是占位，真正用的时候用 grpc/protobuf 解析
            text = raw.decode("utf-8", errors="ignore")
            # 尝试找 JSON 片段
            start = text.find("{")
            if start >= 0:
                # 粗略提取，实际应基于 proto
                return {"raw_text": text[start:start+500], "_note": "简化解析，接入时替换为 protobuf"}
            return None
        except Exception as e:
            logger.debug(f"帧解析失败: {e}")
            return None

    async def start(self):
        """启动监听"""
        if not self.web_rid:
            logger.warning("未配置 DOUYIN_LIVE_WEB_RID，WebSocket 模式不启动")
            return
        self._running = True
        retry = 0
        while self._running and retry < 10:
            try:
                sign = await self._get_sign()
                wss_url = sign["wssUrl"]
                headers = sign.get("headers", {})
                logger.info(f"连接抖音直播间: {self.web_rid}")
                async with websockets.connect(wss_url, additional_headers=headers, ping_interval=None) as ws:
                    self._ws = ws
                    self._heartbeat_task = asyncio.create_task(self._heartbeat(ws))
                    retry = 0
                    async for message in ws:
                        if isinstance(message, bytes):
                            parsed = self._parse_frame(message)
                            if parsed:
                                for h in self.handlers:
                                    try:
                                        await h({
                                            "source": "ws",
                                            "event_type": "unknown",
                                            **parsed,
                                        })
                                    except Exception as e:
                                        logger.error(f"事件处理错误: {e}")
            except Exception as e:
                retry += 1
                logger.error(f"WS 连接失败({retry}/10): {e}")
                await asyncio.sleep(min(30, 2 ** retry))
        self._running = False

    async def stop(self):
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws:
            await self._ws.close()


ws_runner = DouyinWSRunner()
