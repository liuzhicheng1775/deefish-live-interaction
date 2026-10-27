# 大肥鱼直播互动 (deefish-live-interaction)

> 基于 **DeepSeek 大模型** + **抖音开放平台** 的直播间 AI 互动助手。
> 观众进房自动欢迎、弹幕智能回复、礼物感谢——全部由 AI 生成个性化话术。

---

## 这是什么

一个跑在你自己服务器上的中间层：

```
抖音直播间观众
   │
   ├─ 进房/发弹幕/送礼物
   ▼
抖音开放平台 Webhook  ──►  你的 FastAPI 服务  ──►  DeepSeek API 生成回复
   ▲                          │                      │
   │                          ▼                      │
   └── 互动插件卡片展示  ◄──  卡片队列  ◄──────────────┘
```

观众看到的是直播间里弹出的**互动插件卡片**（合规，不直接发弹幕），
卡片内容是 DeepSeek 根据观众弹幕实时生成的回复。

---

## 快速开始

### 1. 安装依赖

```powershell
cd E:\AI\03github\deefish-live-interaction
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

### 3. 配置人设

编辑 `config/persona.yaml`，改成你主播的风格。

### 4. 启动

```powershell
python main.py
```

服务跑在 `http://localhost:8765`。

### 5. 测试

```powershell
# 健康检查
curl http://localhost:8765/health

# 模拟一条弹幕
curl -X POST http://localhost:8765/test/comment -H "Content-Type: application/json" -d "{\"nickname\":\"测试\",\"content\":\"主播你好呀\"}"

# 拉取 AI 生成的卡片
curl http://localhost:8765/cards
```

---

## 接入抖音开放平台（官方合规路径）

### 步骤 1：创建直播小玩法

1. 登录 [抖音开放平台控制台](https://developer.open-douyin.com/)
2. 进入「直播小玩法」→ 「创建直播小玩法」
3. 选择类型：**互动插件**
4. 填写名称，创建

### 步骤 2：配置 Webhook 回调

在控制台「开发配置」里把回调地址填成：

```
https://你的服务器域名/webhook/douyin
```

### 步骤 3：启动数据推送任务

在小玩法后台启动「评论 / 礼物 / 点赞 / 进房」的数据推送任务。
平台会把事件 POST 到你的 `/webhook/douyin`。

### 步骤 4：互动插件前端

用抖音小程序框架写一个简单卡片页，轮询你的 `/cards` 接口，
把 AI 生成的回复以浮层卡片形式展示在直播间。

---

## 目录结构

```
deefish-live-interaction/
├── main.py                    # FastAPI 入口
├── requirements.txt
├── .env.example
├── config/
│   └── persona.yaml            # 人设与话术配置
├── app/
│   ├── config.py              # 配置加载
│   ├── douyin/
│   │   ├── official_webhook.py   # 官方 Webhook 解析
│   │   └── ws_client.py           # 逆向 WS 弹幕（可选增强）
│   ├── ai/
│   │   └── deepseek.py           # DeepSeek 封装 + 记忆 + 限流
│   ├── handlers/
│   │   └── router.py            # 事件路由：欢迎/回复/感谢
│   └── output/
│       └── card_renderer.py      # 卡片渲染
└── logs/
```

---

## 两种模式对比

| | 官方模式（推荐） | 逆向 WS 模式 |
|---|---|---|
| 合规性 | ✅ 完全合规 | ⚠️ 有封号风险 |
| 能力 | 接收事件 + 卡片展示 | 完整弹幕流 |
| 主动发弹幕 | ❌ 不支持 | 需自行对接群控 |
| 适用场景 | 正经商用 | 个人研究测试 |

---

## 关于"进去就有机器人"

你观察到的那个直播间，大概率是：
1. **无人录播**：OBS 循环播放提前录好的视频
2. **AI 弹幕回复**：用逆向 WebSocket 抓弹幕 → AI 生成回复 → 群控发弹幕
3. **水军挂人气**：群控云手机批量进房

这套组合里，"主动发弹幕"这一步是灰产核心，官方API不提供。
本项目走官方路径：**接收弹幕 → AI 生成 → 卡片展示**，合规不踩线。

---

## License

MIT
