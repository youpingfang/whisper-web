"""Whisper 识别核心: 模型缓存 + 切分 + 流式分段识别 + 拼接。

复用了之前在 Streamlit 版验证通过的 split_audio / merge 时间戳偏移逻辑。
"""
import os
import subprocess
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

_MODEL_CACHE = {}
_T2S = None  # 繁转简转换器(惰性加载)


def _ensure_t2s():
    """确保繁转简转换器已加载"""
    global _T2S
    if _T2S is None:
        from opencc import OpenCC
        _T2S = OpenCC('t2s')
    return _T2S


def t2s(text: str) -> str:
    """繁转简"""
    return _ensure_t2s().convert(text) if text else text


def get_model(model_size: str) -> WhisperModel:
    if model_size not in _MODEL_CACHE:
        _MODEL_CACHE[model_size] = WhisperModel(
            model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


def split_audio(file_path: str, chunk_minutes: int):
    """ffmpeg 按固定时长切分, 返回 [(offset_sec, seg_path), ...] 与临时目录"""
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path]).strip())
    chunk = int(chunk_minutes * 60)
    parts = []
    tmp = Path(tempfile.gettempdir()) / f".whisper_chunks_{Path(file_path).stem}"
    tmp.mkdir(parents=True, exist_ok=True)
    start = 0
    i = 0
    while start < dur:
        out = tmp / f"part_{i:03d}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-ss", str(start),
             "-t", str(chunk), "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if out.exists() and out.stat().st_size > 0:
            parts.append((start, str(out)))
        start += chunk
        i += 1
    return parts, tmp


def transcribe_file(file_path, model_size="base", language=None,
                    split_mode="auto", chunk_min=5, use_vad=True):
    """生成器: 逐段 yield 识别文本片段 (用于 SSE 流式推送)。

    yield 字典:
      {"type": "segment", "text": "...", "offset": sec, "start":.., "end":..}
      {"type": "meta", "language": "zh"}
      {"type": "done", "full_text": "...", "files": {txt,srt,vtt}}
    """
    model = get_model(model_size)

    if split_mode == "fixed":
        parts, tmp = split_audio(file_path, chunk_min)
        loader = use_vad
        yield {"type": "progress", "total": len(parts), "mode": "fixed"}
    else:
        parts, tmp = [(0.0, file_path)], None
        loader = True
        yield {"type": "progress", "total": 0, "mode": "auto"}

    all_segments = []   # (offset, [seg,...])
    detected_lang = language
    full = []

    for offset, sp in parts:
        segs, info = model.transcribe(
            sp, language=language, beam_size=5, vad_filter=loader)
        if detected_lang is None:
            detected_lang = info.language
        collected = list(segs)
        all_segments.append((offset, collected))
        for seg in collected:
            txt = t2s(seg.text.strip())
            full.append(txt)
            yield {"type": "segment", "text": txt,
                   "offset": offset, "start": seg.start, "end": seg.end}
        # 清理临时切片
        if tmp is not None and sp != file_path:
            try:
                os.remove(sp)
            except OSError:
                pass

    if tmp is not None:
        try:
            tmp.rmdir()
        except OSError:
            pass

    if not any(s for _, s in all_segments):
        yield {"type": "error", "message": "未识别到任何文字内容"}
        return

    files = _write_outputs(all_segments, file_path)
    yield {"type": "meta", "language": detected_lang}
    yield {"type": "done", "full_text": "".join(full), "files": files}


def _fmt_srt(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_outputs(all_segments, src_path):
    """拼接写出 txt/srt/vtt, 时间戳带偏移累加。返回相对 whisper_files 的下载路径。"""
    out_dir = Path("whisper_files")
    out_dir.mkdir(exist_ok=True)
    base = Path(src_path).stem
    txt = out_dir / f"{base}.txt"
    srt = out_dir / f"{base}.srt"
    vtt = out_dir / f"{base}.vtt"
    idx = 1
    with open(txt, "w", encoding="utf-8") as ft, \
         open(srt, "w", encoding="utf-8") as fs, \
         open(vtt, "w", encoding="utf-8") as fv:
        fv.write("WEBVTT\n\n")
        for offset, segs in all_segments:
            for seg in segs:
                start = offset + seg.start
                end = offset + seg.end
                text = t2s(seg.text.strip())
                ft.write(text + "\n")
                fs.write(f"{idx}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n\n")
                fv.write(f"{_fmt_srt(start).replace(',', '.')} --> "
                         f"{_fmt_srt(end).replace(',', '.')}\n{text}\n\n")
                idx += 1
    return {"txt": str(txt), "srt": str(srt), "vtt": str(vtt)}
