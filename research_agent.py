from __future__ import annotations
import os, re, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
PROFILE_DIR = APP_DIR / ".jarvis-browser-profile"
PORT = int(os.getenv("JARVIS_RESEARCH_PORT", "8765"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
app = FastAPI(title="JARVIS Local Research Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
pool = ThreadPoolExecutor(max_workers=2)
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()

class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    duration_seconds: int = Field(default=10, ge=10, le=60)

def update_job(job_id: str, **values: Any) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(values)
            jobs[job_id]["updated_at"] = time.time()

def compact_text(value: str, limit: int = 3500) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]

def fallback_summary(query: str, pages: list[dict[str, Any]]) -> str:
    if not pages:
        return f"Riset untuk “{query}” belum mengumpulkan isi halaman yang cukup. Periksa koneksi atau coba lagi dengan durasi lebih panjang."
    blocks = [f"{x.get('title', 'Halaman web')}: {compact_text(x.get('text', ''), 900)}"
              for x in pages[:5] if compact_text(x.get("text", ""), 900)]
    return (f"Riset awal: {query}\n\n" + "\n\n".join(blocks) +
            "\n\nCatatan: model AI lokal belum tersedia. Ini kompilasi isi halaman, bukan sintesis AI. Jalankan Ollama untuk laporan analitis.")

def ask_ollama(query: str, pages: list[dict[str, Any]]) -> str | None:
    evidence = [f"JUDUL: {x.get('title', '')}\nISI: {compact_text(x.get('text', ''), 2600)}"
                for x in pages[:8] if compact_text(x.get("text", ""), 2600)]
    if not evidence:
        return None
    prompt = ("Buat laporan riset bahasa Indonesia berdasarkan bahan di bawah. Jangan mengarang angka, tanggal, atau fakta. "
              "Jika bukti kurang, sebutkan keterbatasannya. Struktur: Ringkasan Eksekutif, Temuan Utama, Analisis, "
              "Implikasi, Kesimpulan. Jangan menyebut mesin pencari atau layanan AI yang dipakai.\nTopik: "
              + query + "\n\nBAHAN:\n" + "\n\n".join(evidence))
    try:
        response = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=45)
        if response.ok:
            return str(response.json().get("response", "")).strip() or None
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None

def run_browser_research(job_id: str, query: str, duration: int) -> None:
    start = time.monotonic()
    deadline = start + duration
    pages: list[dict[str, Any]] = []
    images: list[dict[str, str]] = []
    errors: list[str] = []
    context = None
    try:
        from playwright.sync_api import sync_playwright
        update_job(job_id, status="running", progress=5, stage="Membuka browser riset…")
        with sync_playwright() as p:
            PROFILE_DIR.mkdir(exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR), headless=False,
                viewport={"width": 1360, "height": 900},
                args=["--disable-blink-features=AutomationControlled"])
            page = context.pages[0] if context.pages else context.new_page()
            search_url = "https://www.google.com/search?q=" + quote_plus(query)
            update_job(job_id, progress=12, stage="Mencari halaman relevan…", browser_url=search_url)
            page.goto(search_url, wait_until="domcontentloaded", timeout=12000)
            try: page.wait_for_timeout(700)
            except Exception: pass
            try:
                found = page.locator("a:has(h3)").evaluate_all("""els => els.map(a => ({
                    title: (a.querySelector('h3')?.innerText || '').trim(), url: a.href || ''
                })).filter(x => x.title && /^https?:/.test(x.url)
                  && !/google\\.com\\/(search|preferences|accounts)/i.test(x.url))""")
            except Exception as exc:
                found = []
                errors.append("Hasil pencarian tidak bisa dibaca: " + str(exc)[:120])
            seen, targets = set(), []
            for item in found:
                url = item.get("url", "")
                if not url or url in seen: continue
                seen.add(url)
                host = urlparse(url).netloc.lower()
                if host and "google." not in host: targets.append(item)
            targets = targets[:8]
            for index, target in enumerate(targets):
                if time.monotonic() >= deadline or len(pages) >= 6: break
                tab = None
                try:
                    update_job(job_id, progress=min(65, 18 + int(45 * index / max(1, len(targets)))),
                               stage=f"Membaca halaman {index + 1}…", current_title=target["title"][:120])
                    tab = context.new_page()
                    timeout_ms = max(1500, min(6500, int((deadline-time.monotonic())*1000)))
                    tab.goto(target["url"], wait_until="domcontentloaded", timeout=timeout_ms)
                    try: tab.wait_for_timeout(350)
                    except Exception: pass
                    data = tab.evaluate("""() => {
                      const meta = name => document.querySelector('meta[property="' + name + '"],meta[name="' + name + '"]')?.content || '';
                      const main = document.querySelector('main,article,[role="main"]');
                      const root = main || document.body;
                      return {
                        title: document.title || '',
                        description: meta('description') || meta('og:description') || '',
                        image: meta('og:image') || meta('twitter:image') || root?.querySelector('img[src^="http"]')?.src || '',
                        text: (root?.innerText || document.body?.innerText || '').slice(0, 6500)
                      };
                    }""")
                    text = compact_text(data.get("text", ""), 6500)
                    if len(text) > 180:
                        pages.append({"title": compact_text(data.get("title") or target["title"], 220),
                                      "url": target["url"], "description": compact_text(data.get("description", ""), 500),
                                      "text": text, "host": urlparse(target["url"]).netloc})
                        image_url = data.get("image", "")
                        if image_url.startswith("https://") and image_url not in [x["url"] for x in images]:
                            images.append({"url": image_url, "alt": compact_text(data.get("title") or target["title"], 160)})
                except Exception as exc:
                    errors.append("Halaman dilewati: " + str(exc)[:100])
                finally:
                    if tab:
                        try: tab.close()
                        except Exception: pass
            if time.monotonic() < deadline and len(images) < 6:
                image_page = None
                try:
                    update_job(job_id, progress=68, stage="Mengumpulkan visual pendukung…")
                    image_page = context.new_page()
                    image_page.goto("https://www.google.com/search?tbm=isch&q=" + quote_plus(query),
                                    wait_until="domcontentloaded",
                                    timeout=max(1800, min(5000, int((deadline-time.monotonic())*1000))))
                    found_images = image_page.locator("img").evaluate_all("""els => els.map(img => ({
                      url: img.currentSrc || img.src || '', alt: img.alt || ''
                    })).filter(x => /^https?:/.test(x.url) && x.alt && !/google/i.test(x.url)).slice(0, 12)""")
                    for item in found_images:
                        if item["url"] not in [x["url"] for x in images]:
                            images.append({"url": item["url"], "alt": compact_text(item["alt"], 160) or "Visual pendukung"})
                        if len(images) >= 8: break
                except Exception as exc:
                    errors.append("Visual tidak berhasil diambil: " + str(exc)[:100])
                finally:
                    if image_page:
                        try: image_page.close()
                        except Exception: pass
        update_job(job_id, progress=75, stage="Menyusun laporan…")
        summary = ask_ollama(query, pages)
        local_model_used = bool(summary)
        if not summary: summary = fallback_summary(query, pages)
        update_job(job_id, status="completed", progress=100, stage="Laporan siap",
                   result={"query": query, "summary": summary, "pages": pages, "images": images[:8],
                           "elapsed_seconds": round(time.monotonic()-start, 1),
                           "local_model_used": local_model_used, "errors": errors[:5],
                           "notice": "Laporan disusun dengan AI lokal." if local_model_used else
                                     "Ollama tidak merespons; hasil berupa kompilasi halaman yang berhasil dibaca."})
    except Exception as exc:
        update_job(job_id, status="error", progress=100, stage="Riset gagal",
                   error="Browser agent belum siap. Jalankan dependensi dan instal Chromium. Detail: " + str(exc)[:220])
    finally:
        if context:
            try: context.close()
            except Exception: pass

@app.get("/health")
def health() -> dict[str, Any]:
    try: ollama_available = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.5).ok
    except requests.RequestException: ollama_available = False
    return {"ok": True, "service": "JARVIS Local Research Agent", "ollama_available": ollama_available,
            "ollama_model": OLLAMA_MODEL, "browser_profile": str(PROFILE_DIR)}

@app.post("/research")
def start_research(body: ResearchRequest) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0, "stage": "Menyiapkan riset…",
                        "created_at": time.time(), "updated_at": time.time()}
    pool.submit(run_browser_research, job_id, body.query.strip(), body.duration_seconds)
    return {"job_id": job_id}

@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job: raise HTTPException(status_code=404, detail="Job riset tidak ditemukan.")
        return dict(job)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
