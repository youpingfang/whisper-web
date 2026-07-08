# 🎤 Whisper 语音转文字

一个基于 **React + FastAPI + faster-whisper** 的全栈语音转文字应用。支持**上传音频**或**粘贴 B站/YouTube 链接**自动下载并转写，流式输出识别结果，支持中文、长音频自动切分。

## 截图 / 效果

> 暗色/亮色双主题 · 黑白灰阶极简风格 · 流式实时出字 · 复制/下载一键完成

## 功能

| 功能 | 说明 |
|------|------|
| 🎵 **上传音频** | MP3 / WAV / MP4 / M4A / FLAC / OGG |
| 🔗 **粘贴链接** | 支持 B站 / YouTube（B站需 cookies） |
| 🌐 **中文识别** | 默认中文，支持多语言 + 自动检测 |
| ⏱ **流式输出** | SSE 实时推送，边识别边显示文字 |
| 📄 **字幕导出** | TXT / SRT / VTT 三种格式一键下载 |
| 📋 **全文复制** | 一键复制识别结果 |
| ✂️ **长音频切分** | VAD 自动分段或固定时长切分 + 时间戳偏移拼接 |
| 🌗 **暗/亮主题** | 右上角一键切换，自动记忆到 localStorage |
| ♻️ **刷新保留** | 转写结果存入 sessionStorage，刷新不丢 |

## 技术栈

```
whisper-web/
├── backend/                    # Python 后端
│   ├── main.py                 FastAPI + SSE 流式 (@ 8000)
│   ├── core.py                 faster-whisper 模型 + 切分 + 拼接
│   └── whisper_files/          转写结果输出目录
│
├── frontend/                   # React 前端
│   ├── src/App.tsx             两栏布局 + 流式消费 + 暗/亮切换
│   ├── src/index.css           设计令牌 (黑白灰阶, CSS 变量)
│   └── src/components/ui/      卡片/按钮/徽章组件
│
└── README.md
```

| 层 | 技术 |
|----|------|
| **前端** | React 19, Vite 7, Tailwind CSS 4, TypeScript, pnpm |
| **后端** | FastAPI, uvicorn, SSE (sse-starlette) |
| **引擎** | faster-whisper (CPU/int8), CTranslate2 |
| **下载** | yt-dlp (YouTube/B站) |
| **音频** | ffmpeg |

## 快速启动

### 前置要求
- Python 3.12+
- Node.js 22+
- pnpm（`npm install -g pnpm`）
- ffmpeg（`apt install ffmpeg`）

### 后端
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" python-multipart faster-whisper sse-starlette yt-dlp
python main.py
# → http://localhost:8000
```

### 前端
```bash
cd frontend
pnpm install
pnpm dev
# → http://localhost:5173
```

前端 Vite 开发服务器自动代理 `/api` 到后端 8000 端口。

### 生产构建
```bash
cd frontend
pnpm run build
# → dist/ 目录可直接部署
```

## B站 链接使用说明

⚠️ B站 有反爬机制，直接粘贴 B站 链接会提示"需要登录 cookies"。

**解决：导出浏览器 cookies**
1. 在 Chrome 中登录 [bilibili.com](https://www.bilibili.com)
2. 安装 [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid) 扩展
3. 在 B站 页面点击扩展 → 导出 `cookies.txt`
4. 将文件上传到 `backend/bili_cookies.txt`
5. 重新粘贴 B站 链接即可下载

> YouTube 链接无需额外配置，直接可用。

## API 文档

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/transcribe` | POST | 上传音频文件转写 |
| `/api/transcribe-url` | POST | 粘贴视频链接转写 |
| `/api/download/{kind}/{filename}` | GET | 下载字幕文件 |

### POST `/api/transcribe`

**参数** (multipart/form-data):
- `file` — 音频文件
- `model` — 模型 (tiny/base/small/medium/large-v3, 默认 base)
- `language` — 识别语言 (zh/auto/en/ja/ko/yue, 默认 zh)
- `split_mode` — 切分方式 (auto/fixed, 默认 auto)
- `chunk_min` — 固定切分每段分钟数 (默认 5)
- `use_vad` — VAD 过滤 (true/false, 默认 true)

**返回**: SSE 事件流
```
event: message
data: {"type":"segment","text":"识别文字...","offset":0,"start":0.0,"end":2.4}

event: message
data: {"type":"meta","language":"zh"}

event: message
data: {"type":"done","full_text":"...","files":{"txt":"...","srt":"...","vtt":"..."}}
```

## 许可证

MIT
