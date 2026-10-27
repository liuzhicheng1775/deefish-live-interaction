"""DeepSeek API 封装：带人设、上下文记忆、限流"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

import httpx
from loguru import logger

from app.config import get_env, get_persona


# 简单内存记忆：每个用户保留最近 N 条对话
class MemoryStore:
    def __init__(self, max_turns: int = 10):
        self._store: dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=max_turns))

    def add(self, user_id: str, role: str, content: str):
        self._store[user_id].append({"role": role, "content": content})

    def history(self, user_id: str) -> list[dict]:
        return list(self._store[user_id])


memory = MemoryStore(max_turns=8)


class DeepSeekClient:
    def __init__(self):
        env = get_env()
        self.api_key = env.deepseek_api_key
        self.base_url = env.deepseek_base_url.rstrip("/")
        self.model = env.deepseek_model
        self.temperature = env.ai_temperature
        self.max_chars = env.ai_max_reply_chars
        self._persona = get_persona().get("persona", {})
        self._client = httpx.AsyncClient(timeout=15.0)

    def _system_prompt(self) -> str:
        p = self._persona
        return (
            f"你是{ p.get('name', '直播间助手') }，{ p.get('role', '') }。\n"
            f"{ p.get('style', '') }\n"
            f"注意：回复必须在 { self.max_chars } 字以内，不要用 markdown，直接输出要说的话。"
        )

    async def _chat(self, messages: list[dict]) -> str:
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置，返回占位回复")
            return "（AI未配置）你好呀～"
        try:
            resp = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": 120,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"DeepSeek 调用失败: {e}")
            return ""

    async def welcome(self, nickname: str) -> str:
        """生成进房欢迎语"""
        msgs = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": f"观众「{nickname}」刚进入直播间，请用一句话欢迎他（20字内，热情一点）。"},
        ]
        text = await self._chat(msgs)
        return text or f"欢迎 {nickname} 来到直播间！"

    async def reply_comment(self, user_id: str, nickname: str, comment: str) -> str:
        """对弹幕生成智能回复"""
        history = memory.history(user_id)
        msgs = [{"role": "system", "content": self._system_prompt()}]
        msgs.extend(history)
        msgs.append({"role": "user", "content": f"观众「{nickname}」说：{comment}"})
        text = await self._chat(msgs)
        if text:
            memory.add(user_id, "user", comment)
            memory.add(user_id, "assistant", text)
        return text

    async def thank_gift(self, nickname: str, gift_name: str, count: int) -> str:
        """礼物感谢语"""
        msgs = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": f"观众「{nickname}」送了 {count} 个「{gift_name}」，请说一句简短真诚的感谢（25字内）。"},
        ]
        return await self._chat(msgs)

    async def aclose(self):
        await self._client.aclose()


# 全局单例
ai = DeepSeekClient()


# 简单限流：内存版
class RateLimiter:
    def __init__(self):
        self._user_last: dict[str, float] = {}
        self._global_times: deque = deque()

    def allow(self, user_id: str, per_user_sec: int, global_per_min: int) -> bool:
        now = time.time()
        # 用户级
        last = self._user_last.get(user_id, 0)
        if now - last < per_user_sec:
            return False
        # 全局级
        while self._global_times and now - self._global_times[0] > 60:
            self._global_times.popleft()
        if len(self._global_times) >= global_per_min:
            return False
        self._user_last[user_id] = now
        self._global_times.append(now)
        return True


limiter = RateLimiter()
