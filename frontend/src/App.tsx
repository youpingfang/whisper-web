import { useRef, useState, useEffect } from 'react'
import { UploadCloud, Copy, Download, AudioLines, Check, Loader2, Sun, Moon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Button, Badge, Progress, Textarea } from '@/components/ui/primitives'

type Seg = { text: string; offset: number; start: number; end: number }
type Status = 'idle' | 'transcribing' | 'done' | 'error'

const MODELS = [
  { v: 'tiny', label: 'Tiny · 最快/低精度' },
  { v: 'base', label: 'Base · 均衡' },
  { v: 'small', label: 'Small · 更准' },
  { v: 'medium', label: 'Medium · 高准' },
  { v: 'large-v3', label: 'Large-v3 · 最高准' },
]
const LANGS = [
  { v: 'zh', label: '中文' },
  { v: 'auto', label: '自动检测' },
  { v: 'en', label: '英语' },
  { v: 'ja', label: '日语' },
  { v: 'ko', label: '韩语' },
  { v: 'yue', label: '粤语' },
]

export default function App() {
  const [inputMode, setInputMode] = useState<'file' | 'url'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [model, setModel] = useState('base')
  const [language, setLanguage] = useState('zh')
  const [splitMode, setSplitMode] = useState('auto')
  const [chunkMin, setChunkMin] = useState(5)
  const [useVad, setUseVad] = useState(true)

  const [status, setStatus] = useState<Status>(() => {
    const saved = sessionStorage.getItem('whisper-status')
    return saved === 'done' ? 'done' : 'idle'
  })
  const [segments, setSegments] = useState<Seg[]>([])
  const [fullText, setFullText] = useState(() => {
    return sessionStorage.getItem('whisper-text') || ''
  })
  const [detectedLang, setDetectedLang] = useState(() => {
    return sessionStorage.getItem('whisper-lang') || ''
  })
  const [files, setFiles] = useState<{ txt: string; srt: string; vtt: string } | null>(() => {
    const raw = sessionStorage.getItem('whisper-files')
    return raw ? JSON.parse(raw) : null
  })
  const [progress, setProgress] = useState(0)
  const [copied, setCopied] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  // 主题: 暗色/亮色切换, 记忆到 localStorage
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('whisper-theme')
    return saved === 'light' ? 'light' : 'dark'
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('whisper-theme', theme)
  }, [theme])

  // 转写结果持久化: 刷新页面保留已完成结果
  useEffect(() => {
    if (status === 'done') {
      sessionStorage.setItem('whisper-status', 'done')
      sessionStorage.setItem('whisper-text', fullText)
      sessionStorage.setItem('whisper-lang', detectedLang)
      if (files) sessionStorage.setItem('whisper-files', JSON.stringify(files))
    }
  }, [status, fullText, detectedLang, files])

  const totalChars = fullText.length
  const segCount = segments.length

  async function start() {
    if (inputMode === 'file' && !file) return
    if (inputMode === 'url' && !url.trim()) return
    setStatus('transcribing')
    setSegments([])
    setFullText('')
    setFiles(null)
    setDetectedLang('')
    setErrorMsg('')
    setProgress(0)
    setCopied(false)

    const form = new FormData()
    if (inputMode === 'file') {
      form.append('file', file!)
    } else {
      form.append('url', url.trim())
    }
    form.append('model', model)
    form.append('language', language)
    form.append('split_mode', splitMode)
    form.append('chunk_min', String(chunkMin))
    form.append('use_vad', String(useVad))

    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      const endpoint = inputMode === 'file' ? '/api/transcribe' : '/api/transcribe-url'
      const res = await fetch(endpoint, { method: 'POST', body: form, signal: ctrl.signal })
      if (!res.ok || !res.body) {
        let detail = ''
        try { const j = await res.json(); detail = j.error || j.detail || '' } catch {}
        throw new Error(detail || `请求失败 ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          const t = line.trim()
          if (!t.startsWith('data:')) continue
          const payload = t.slice(5).trim()
          if (!payload || payload === '[DONE]') continue
          let msg: any
          try {
            msg = JSON.parse(payload)
          } catch {
            continue
          }
          if (msg.type === 'segment') {
            setSegments((prev) => [...prev, msg])
            setFullText((prev) => prev + msg.text)
          } else if (msg.type === 'meta') {
            setDetectedLang(msg.language)
          } else if (msg.type === 'done') {
            setFullText(msg.full_text)
            setFiles(msg.files)
            setStatus('done')
          } else if (msg.type === 'error') {
            setErrorMsg(msg.message)
            setStatus('error')
          }
        }
      }
      setProgress(100)
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setErrorMsg(e.message || '出错了')
        setStatus('error')
      }
    }
  }

  function copyAll() {
    // HTTP 环境下 navigator.clipboard 不可用, 改用 execCommand 兼容方案
    const ta = document.createElement('textarea')
    ta.value = fullText
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch (e) {
      console.error('复制失败', e)
    }
    document.body.removeChild(ta)
  }

  function dl(kind: 'txt' | 'srt' | 'vtt') {
    if (!files) return
    const name = files[kind].split('/').pop()
    window.open(`/api/download/${kind}/${name}`, '_blank')
  }

  return (
    <div className="mx-auto max-w-[1600px] px-10 py-10">
      {/* 顶部标题 */}
      <header className="mb-8 flex items-center justify-between">
        <div className="text-center flex-1">
          <div className="flex items-center justify-center gap-2 text-[var(--color-ink)]">
            <AudioLines size={26} />
            <h1 className="text-2xl font-light tracking-wide">Whisper 语音转文字</h1>
          </div>
          <p className="mt-1 text-base font-normal text-[var(--color-ink-dim)]">
            CPU 本地识别 · 支持中文 · 长音频自动切分
          </p>
        </div>
        <Button variant="outline" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="shrink-0" aria-label="切换明暗主题">
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          {theme === 'dark' ? '亮色' : '暗色'}
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {/* ===== 左栏：输入 ===== */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>输入方式</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-3">
                <button onClick={() => setInputMode('file')}
                  className={`flex-1 rounded-[9px] border px-3 py-2 text-base font-normal transition-colors ${
                    inputMode === 'file'
                      ? 'border-[var(--color-selected-bg)] bg-[var(--color-selected-bg)] text-[var(--color-selected-fg)] font-semibold'
                      : 'border-[var(--color-border-soft)] text-[var(--color-ink-dim)] hover:border-[var(--color-border-strong)]'
                  }`}>上传音频</button>
                <button onClick={() => setInputMode('url')}
                  className={`flex-1 rounded-[9px] border px-3 py-2 text-base font-normal transition-colors ${
                    inputMode === 'url'
                      ? 'border-[var(--color-selected-bg)] bg-[var(--color-selected-bg)] text-[var(--color-selected-fg)] font-semibold'
                      : 'border-[var(--color-border-soft)] text-[var(--color-ink-dim)] hover:border-[var(--color-border-strong)]'
                  }`}>粘贴链接</button>
              </div>
              {inputMode === 'file' ? (
                <label className="flex cursor-pointer items-center gap-2 rounded-[9px] border border-[var(--color-border-soft)] bg-[var(--color-surface-2)] px-4 py-3 text-base transition-colors hover:border-[var(--color-border-strong)]">
                  <UploadCloud size={20} className="shrink-0 text-[var(--color-ink-dim)]" />
                  <span className="flex-1 truncate text-[var(--color-ink)]">
                    {file ? file.name : '拖拽或点击选择音频文件'}
                  </span>
                  <input type="file" accept="audio/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                </label>
              ) : (
                <div className="space-y-3">
                  <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="粘贴 B站 / YouTube 视频链接…"
                    className="w-full rounded-[9px] border border-[var(--color-border-soft)] bg-[var(--color-surface-2)] px-4 py-3 text-base outline-none text-[var(--color-ink)] focus:border-[var(--color-border-strong)] placeholder:text-[var(--color-ink-mut)]" />
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>识别参数</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="mb-1.5 block text-base font-normal text-[var(--color-ink-dim)]">模型</label>
                <div className="grid grid-cols-2 gap-2">
                  {MODELS.map((m) => (
                    <button
                      key={m.v}
                      onClick={() => setModel(m.v)}
                      className={`rounded-[9px] border px-3 py-2 text-left text-base font-normal transition-colors ${
                        model === m.v
                          ? 'border-[var(--color-selected-bg)] bg-[var(--color-selected-bg)] text-[var(--color-selected-fg)] font-semibold'
                          : 'border-[var(--color-border-soft)] text-[var(--color-ink-dim)] hover:border-[var(--color-border-strong)]'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-base font-normal text-[var(--color-ink-dim)]">语言</label>
                <div className="flex flex-wrap gap-2">
                  {LANGS.map((l) => (
                    <button
                      key={l.v}
                      onClick={() => setLanguage(l.v)}
                      className={`rounded-full border px-3 py-1 text-base font-normal transition-colors ${
                        language === l.v
                          ? 'border-[var(--color-selected-bg)] bg-[var(--color-selected-bg)] text-[var(--color-selected-fg)] font-semibold'
                          : 'border-[var(--color-border-soft)] text-[var(--color-ink-dim)] hover:border-[var(--color-border-strong)]'
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-base font-normal text-[var(--color-ink-dim)]">切分方式</label>
                <div className="flex gap-2">
                  {[
                    { v: 'auto', label: '自动 (VAD)' },
                    { v: 'fixed', label: '固定时长' },
                  ].map((s) => (
                    <button
                      key={s.v}
                      onClick={() => setSplitMode(s.v)}
                      className={`flex-1 rounded-[9px] border px-3 py-2 text-base font-normal transition-colors ${
                        splitMode === s.v
                          ? 'border-[var(--color-selected-bg)] bg-[var(--color-selected-bg)] text-[var(--color-selected-fg)] font-semibold'
                          : 'border-[var(--color-border-soft)] text-[var(--color-ink-dim)]'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                {splitMode === 'fixed' && (
                  <div className="mt-2 flex items-center gap-2 text-base font-normal text-[var(--color-ink-dim)]">
                    <span>每段</span>
                    <input
                      type="number"
                      min={1}
                      max={60}
                      value={chunkMin}
                      onChange={(e) => setChunkMin(Number(e.target.value))}
                      className="w-16 rounded-[6px] border border-[var(--color-border-soft)] bg-[var(--color-surface-2)] px-2 py-1 text-center outline-none"
                    />
                    <span>分钟</span>
                  </div>
                )}
              </div>

              <label className="flex items-center gap-2 text-base font-normal text-[var(--color-ink-dim)]">
                <input
                  type="checkbox"
                  checked={useVad}
                  onChange={(e) => setUseVad(e.target.checked)}
                  className="accent-[var(--color-primary)]"
                />
                启用 VAD 过滤（跳过静音段）
              </label>

              <Button
                className="w-full"
                disabled={(inputMode === 'file' ? !file : !url.trim()) || status === 'transcribing'}
                onClick={start}
              >
                {status === 'transcribing' ? (
                  <>
                    <Loader2 size={16} className="animate-spin" /> 识别中…
                  </>
                ) : (
                  '开始转写'
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* ===== 右栏：输出 ===== */}
        <div className="space-y-4">
          <Card className="flex h-full flex-col">
            <CardHeader className="flex items-center justify-between">
              <CardTitle>识别结果</CardTitle>
              {status === 'done' && (
                <div className="flex flex-wrap gap-2">
                  <Badge>✓ 完成</Badge>
                  {detectedLang && <Badge>语言: {detectedLang}</Badge>}
                  <Badge>字符: {totalChars}</Badge>
                  <Badge>分段: {segCount}</Badge>
                </div>
              )}
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              {status === 'transcribing' && <Progress value={progress} />}
              {status === 'idle' && (
                <p className="font-light text-[var(--color-ink-mut)]">
                  转写结果将在这里实时显示……
                </p>
              )}
              {status === 'error' && (
                <p className="font-light text-[var(--color-warn)]">出错：{errorMsg}</p>
              )}
              <Textarea
                readOnly
                value={fullText}
                placeholder=""
                className={`min-h-[480px] flex-1 ${status === 'transcribing' && fullText ? 'caret' : ''}`}
              />
              {status === 'done' && (
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" onClick={copyAll}>
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                    {copied ? '已复制' : '复制全文'}
                  </Button>
                  <Button variant="outline" onClick={() => dl('txt')}>
                    <Download size={16} /> TXT
                  </Button>
                  <Button variant="outline" onClick={() => dl('srt')}>
                    <Download size={16} /> SRT
                  </Button>
                  <Button variant="outline" onClick={() => dl('vtt')}>
                    <Download size={16} /> VTT
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
