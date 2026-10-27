"""配置加载：合并 .env 环境变量 + persona.yaml 人设配置"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 抖音开放平台
    douyin_client_key: str = ""
    douyin_client_secret: str = ""
    douyin_app_id: str = ""
    douyin_webhook_verify_token: str = ""

    # 逆向 WS 模式
    douyin_sign_api_url: str = ""
    douyin_cookie: str = ""
    douyin_live_web_rid: str = ""

    # 服务
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"

    # 限流
    rate_limit_per_user_sec: int = 10
    rate_limit_global_per_min: int = 60
    ai_temperature: float = 0.8
    ai_max_reply_chars: int = 60


@lru_cache
def get_env() -> EnvSettings:
    return EnvSettings()


@lru_cache
def get_persona() -> dict:
    """加载 persona.yaml"""
    path = BASE_DIR / "config" / "persona.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
