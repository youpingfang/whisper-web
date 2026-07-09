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
        yield {"event": "message", "data": json.dumps(
            {"type": "status", "stage": "saving", "text": "文件已保存，开始识别…"}, ensure_ascii=False)}
        yield {"event": "message", "data": json.dumps(
            {"type": "status", "stage": "transcribing", "text": "正在识别…"}, ensure_ascii=False)}
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
    """接收 B站/YouTube 链接 → yt-dlp 下载音频 → 转写 (SSE 流式推送全流程状态)"""
    vid = uuid.uuid4().hex

    async def event_gen():
        import asyncio
        loop = asyncio.get_event_loop()

        # 1. 下载阶段
        yield {"event": "message", "data": json.dumps(
            {"type": "status", "stage": "downloading", "text": "正在下载音频…"}, ensure_ascii=False)}

        cookies_dir = Path("cookies")
        cookies_files = sorted(cookies_dir.glob("*.txt")) if cookies_dir.is_dir() else []
        if not cookies_files:
            old = Path("bili_cookies.txt")
            if old.exists():
                cookies_files = [old]
        cookies_opts = []
        for cf in cookies_files:
            cookies_opts = ["--cookies", str(cf)]

        audio_path = DOWNLOAD_DIR / f"{vid}.%(ext)s"
        try:
            subprocess.run(
                ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
                 "--extract-audio", "--audio-format", "mp3",
                 *cookies_opts, "-o", str(audio_path), url],
                capture_output=True, check=True, timeout=600)
        except subprocess.TimeoutExpired:
            yield {"event": "message", "data": json.dumps(
                {"type": "error", "message": "下载超时: 视频音频下载超过 10 分钟，请稍后重试"}, ensure_ascii=False)}
            return
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode()
            if "412" in stderr or "Unable to download webpage" in stderr:
                yield {"event": "message", "data": json.dumps(
                    {"type": "error", "message": "B站/视频站需要登录 cookies 才能下载。请在浏览器登录B站，导出 cookies.txt 文件并上传。",
                     "detail": stderr[:300]}, ensure_ascii=False)}
            else:
                yield {"event": "message", "data": json.dumps(
                    {"type": "error", "message": f"下载失败: {stderr[:200]}"}, ensure_ascii=False)}
            return

        mp3_path = DOWNLOAD_DIR / f"{vid}.mp3"
        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            yield {"event": "message", "data": json.dumps(
                {"type": "error", "message": "下载音频失败，未生成文件"}, ensure_ascii=False)}
            return

        # 2. 转写阶段
        yield {"event": "message", "data": json.dumps(
            {"type": "status", "stage": "transcribing", "text": "正在识别…"}, ensure_ascii=False)}

        lang = None if language == "auto" else language
        gen = transcribe_file(
            str(mp3_path), model_size=model, language=lang,
            split_mode=split_mode, chunk_min=chunk_min, use_vad=use_vad)
        for item in gen:
            yield {"event": "message", "data": json.dumps(item, ensure_ascii=False)}
        # 清理
        for f in DOWNLOAD_DIR.glob(f"{vid}.*"):
            try:
                os.remove(str(f))
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
