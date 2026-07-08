"""FastAPI 后端: 接收音频, SSE 流式推送识别结果, 提供字幕下载。"""
import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from core import transcribe_file

app = FastAPI(title="Whisper Web API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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
    # 保存上传文件
    ext = Path(file.filename).suffix or ".mp3"
    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / save_name
    with open(save_path, "wb") as f:
        f.write(await file.read())

    lang = None if language == "auto" else language

    async def event_gen():
        # transcribe_file 是同步生成器, 用线程避免阻塞事件循环
        import asyncio
        loop = asyncio.get_event_loop()
        gen = transcribe_file(
            str(save_path), model_size=model, language=lang,
            split_mode=split_mode, chunk_min=chunk_min, use_vad=use_vad)
        for item in gen:
            yield {"event": "message", "data": json.dumps(item, ensure_ascii=False)}
        # 清理上传原件
        try:
            os.remove(save_path)
        except OSError:
            pass

    return EventSourceResponse(event_gen())


@app.get("/api/download/{kind}/{filename}")
def download(kind: str, filename: str):
    base = Path("whisper_files")
    path = base / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media = "text/plain" if kind == "txt" else "text/vtt" if kind == "vtt" else "text/plain"
    return FileResponse(path, media_type=media, filename=filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
