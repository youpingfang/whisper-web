"""FastAPI 后端: 接收音频/链接, SSE 流式推送识别结果, 提供字幕下载。"""
import os
import json
import uuid
import subprocess
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from core import transcribe_file

app = FastAPI(title="Whisper Web API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
# Docker 或生产环境下, 前端静态文件在 /app/static
STATIC_DIR = Path("/app/static")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: str = Form("zh"),
    split_mode: str = Form("auto"),
    chunk_min: int = Form(5),
    use_vad: bool = Form(True),
):
    ext = Path(file.filename).suffix or ".mp3"
    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / save_name
    with open(save_path, "wb") as f:
        f.write(await file.read())

    lang = None if language == "auto" else language

    async def event_gen():
        import asyncio
        loop = asyncio.get_event_loop()
        gen = transcribe_file(
            str(save_path), model_size=model, language=lang,
            split_mode=split_mode, chunk_min=chunk_min, use_vad=use_vad)
        for item in gen:
            yield {"event": "message", "data": json.dumps(item, ensure_ascii=False)}
        try:
            os.remove(save_path)
        except OSError:
            pass

    return EventSourceResponse(event_gen())


@app.post("/api/transcribe-url")
async def transcribe_url(
    url: str = Form(...),
    model: str = Form("base"),
    language: str = Form("zh"),
    split_mode: str = Form("auto"),
    chunk_min: int = Form(5),
    use_vad: bool = Form(True),
):
    """接收 B站/YouTube 链接 → yt-dlp 下载视频 → ffmpeg 提取音频 → 转写"""
    vid = uuid.uuid4().hex
    video_path = DOWNLOAD_DIR / f"{vid}.mp4"

    # 扫描 cookies 目录下的所有 .txt 文件, 自动逐个尝试
    cookies_dir = Path("cookies")
    cookies_files = sorted(cookies_dir.glob("*.txt")) if cookies_dir.is_dir() else []
    if not cookies_files:
        old = Path("bili_cookies.txt")
        if old.exists():
            cookies_files = [old]
    cookies_opts = []
    for cf in cookies_files:
        cookies_opts = ["--cookies", str(cf)]

    # yt-dlp 下载视频 (优先 mp4)
    try:
        subprocess.run(
            ["yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
             "--merge-output-format", "mp4",
             *cookies_opts, "-o", str(video_path), url],
            capture_output=True, check=True, timeout=300)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode()
        # 如果合并失败, 降级下载任何格式
        if "Requested format is not available" in stderr or "merge" in stderr:
            try:
                subprocess.run(
                    ["yt-dlp", "-f", "best", *cookies_opts, "-o", str(video_path), url],
                    capture_output=True, check=True, timeout=300)
            except subprocess.CalledProcessError as e2:
                stderr = e2.stderr.decode()
                if "412" in stderr or "Unable to download webpage" in stderr:
                    return JSONResponse(
                        {"error": "B站/视频站需要登录 cookies 才能下载。"
                                  "请先在浏览器登录B站，导出 cookies.txt 文件并上传到页面中。",
                         "detail": stderr[:300]},
                        status_code=400)
                return JSONResponse({"error": f"下载失败: {stderr[:200]}"}, status_code=400)
        elif "412" in stderr or "Unable to download webpage" in stderr:
            return JSONResponse(
                {"error": "B站/视频站需要登录 cookies 才能下载。"
                          "请先在浏览器登录B站，导出 cookies.txt 文件并上传到页面中。",
                 "detail": stderr[:300]},
                status_code=400)
        return JSONResponse({"error": f"下载失败: {stderr[:200]}"}, status_code=400)

    # ffmpeg 提取音频
    audio_path = DOWNLOAD_DIR / f"{vid}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-q:a", "0", "-map", "a", str(audio_path)],
        capture_output=True, check=True)

    # 确认视频存在
    if not video_path.exists() or video_path.stat().st_size == 0:
        return JSONResponse({"error": "下载视频失败，未生成文件"}, status_code=400)

    lang = None if language == "auto" else language

    async def event_gen():
        import asyncio
        loop = asyncio.get_event_loop()
        gen = transcribe_file(
            str(audio_path), model_size=model, language=lang,
            split_mode=split_mode, chunk_min=chunk_min, use_vad=use_vad)
        for item in gen:
            # 在 done 事件中附加视频路径
            if item["type"] == "done":
                item["video"] = f"{vid}.mp4"
            yield {"event": "message", "data": json.dumps(item, ensure_ascii=False)}
        try:
            os.remove(audio_path)  # 只删音频, 保留视频
        except OSError:
            pass

    return EventSourceResponse(event_gen())


@app.get("/api/download/{kind}/{filename}")
def download(kind: str, filename: str):
    if kind == "video":
        path = DOWNLOAD_DIR / filename
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path, media_type="video/mp4", filename=filename)
    base = Path("whisper_files")
    path = base / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media = "text/plain" if kind == "txt" else "text/vtt" if kind == "vtt" else "text/plain"
    return FileResponse(path, media_type=media, filename=filename)


# Docker 生产模式: 前端静态文件 catch-all (API 路由优先, 放在最后)
if STATIC_DIR.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        return JSONResponse({"error": "not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
