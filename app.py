from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
import json
import time
from concurrent.futures import ThreadPoolExecutor
import asyncio

app = FastAPI()

# --- КОНФИГУРАЦИЯ ---
API_BASE = "https://anilibria.top/api/v1"
USER_AGENT = "AniLiberty-Prowlarr-Bridge/5.7"
TIMEOUT = 30

# --- КЕШИРОВАНИЕ ---
cache = {}
CACHE_TTL = 300  # 5 минут

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MIDDLEWARE ДЛЯ ЛОГИРОВАНИЯ ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"=== REQUEST ===")
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Path: {request.url.path}")
    print(f"Query: {dict(request.query_params)}")
    
    response = await call_next(request)
    
    print(f"=== RESPONSE ===")
    print(f"Status: {response.status_code}")
    
    return response

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_xml_bytes(elem):
    """Превращает объект XML в байты."""
    return ET.tostring(elem, encoding="utf-8", xml_declaration=True)

def create_empty_rss():
    """Создает пустой RSS ответ."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "AniLibria"
    ET.SubElement(channel, "description").text = "No results found"
    return rss

def get_cached(key, fetch_func, *args, **kwargs):
    """Получает данные из кеша или через функцию."""
    current_time = time.time()
    if key in cache:
        data, timestamp = cache[key]
        if current_time - timestamp < CACHE_TTL:
            return data
    
    data = fetch_func(*args, **kwargs)
    if data:
        cache[key] = (data, current_time)
    return data

# --- ФУНКЦИИ ПОЛУЧЕНИЯ ДАННЫХ ---
def fetch_release_metadata(release_id: int) -> Optional[dict]:
    """Получает необходимые метаданные релиза по его ID (для RSS)."""
    cache_key = f"release_{release_id}"
    return get_cached(cache_key, _fetch_release_metadata, release_id)

def _fetch_release_metadata(release_id: int) -> Optional[dict]:
    fields_to_include = "id,name,alias,poster,episodes_total,updated_at"
    url = f"{API_BASE}/anime/releases/{release_id}?include={fields_to_include}&exclude=description,franchises,torrents"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"ERROR: Failed to fetch release metadata {release_id}: {e}")
        return None

def fetch_release_with_torrents(release_id: int) -> Optional[dict]:
    """Получает полный объект релиза и все его торренты."""
    cache_key = f"release_full_{release_id}"
    return get_cached(cache_key, _fetch_release_with_torrents, release_id)

def _fetch_release_with_torrents(release_id: int) -> Optional[dict]:
    fields_to_include = "id,name,alias,poster,episodes_total,updated_at,torrents"
    url = f"{API_BASE}/anime/releases/{release_id}?include={fields_to_include}&exclude=description,franchises"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"ERROR: Failed to fetch full release with torrents {release_id}: {e}")
        return None

def fetch_latest_torrents(limit: int = 50) -> list:
    """Получает список последних торрентов."""
    cache_key = f"latest_torrents_{limit}"
    return get_cached(cache_key, _fetch_latest_torrents, limit)

def _fetch_latest_torrents(limit: int = 50) -> list:
    api_limit = min(limit, 50)
    url = f"{API_BASE}/anime/torrents"
    headers = {"User-Agent": USER_AGENT}
    base_params = {"limit": api_limit}
    
    try:
        resp = requests.get(url, params=base_params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        items_candidate = data.get('torrents', items)
        
        if isinstance(items_candidate, dict):
            items = list(items_candidate.values())
        elif isinstance(items_candidate, list):
            items = items_candidate

        final_items = [item for item in items if isinstance(item, dict) and 'id' in item]
        return final_items
    except Exception as e:
        print(f"ERROR: Fetching latest torrents failed: {e}")
        return []

def fetch_releases(query: str = None, limit: int = 50) -> list:
    """Получает список релизов по поисковому запросу."""
    cache_key = f"search_{query}_{limit}"
    return get_cached(cache_key, _fetch_releases, query, limit)

def _fetch_releases(query: str = None, limit: int = 50) -> list:
    headers = {"User-Agent": USER_AGENT}
    try:
        url = f"{API_BASE}/app/search/releases"
        resp = requests.get(url, params={"limit": limit, "query": query}, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        final_items = []
        
        def recursive_flatten(obj):
            if isinstance(obj, dict):
                if "release" in obj and isinstance(obj["release"], dict):
                    final_items.append(obj["release"])
                    return
                if "id" in obj and "name" in obj:
                    final_items.append(obj)
                    return
                for value in obj.values():
                    recursive_flatten(value)
            elif isinstance(obj, list):
                for element in obj:
                    recursive_flatten(element)
        
        recursive_flatten(items)
        return final_items
    except Exception as e:
        print(f"ERROR: Fetching data failed: {e}")
        return []

# --- build_rss_item ---
def build_rss_item(release, torrent):
    item = ET.Element("item")
    name_obj = release.get("name", {})
    
    # 1. Получаем Русское и Английское названия
    ru_title = name_obj.get("main", "Unknown Series").strip()
    en_title = name_obj.get("english", ru_title).strip()
    
    quality = "Unknown"
    if "quality" in torrent and isinstance(torrent["quality"], dict):
        quality = torrent["quality"].get("description", torrent["quality"].get("value", ""))
    elif "quality" in torrent:
        quality = str(torrent["quality"])
    
    size_bytes = torrent.get("size", 0)
    torrent_id = torrent.get("id")
    
    # 2. Формируем базовый заголовок
    base_title = f"{ru_title} ({en_title})"
    full_title = base_title.strip()
    
    # 3. Episode/Part Info
    ep_info = torrent.get("description", "") or ""
    ep_info = (ep_info
               .replace('[Фильм]', '')
               .replace('[Спешл]', '')
               .replace('[OVA]', '')
               .replace('/', '')
               .strip())
    
    if not ep_info:
        episodes_total = release.get('episodes_total')
        if episodes_total and episodes_total > 0:
            ep_info = f"1-{episodes_total}"
        else:
            ep_info = ""
    
    if ep_info:
        cleaned_ep_info = ep_info.strip().replace('[', '').replace(']', '').replace(' ', '')
        
        if any(char in cleaned_ep_info for char in ['-', ',']):
            if '-' in cleaned_ep_info:
                try:
                    start, end = map(int, cleaned_ep_info.split('-'))
                    full_title += f" E{start:02d}-E{end:02d}"
                except ValueError:
                    full_title += f" {cleaned_ep_info}"
            else:
                full_title += f" {cleaned_ep_info}"
        elif cleaned_ep_info.isdigit() and len(cleaned_ep_info) <= 3:
            full_title += f" E{int(cleaned_ep_info):02d}"
        elif cleaned_ep_info:
            full_title += f" [{cleaned_ep_info}]"
    
    # 4. Add Language Tag
    full_title += " [Rus]"
    
    # 5. Add Quality
    if quality and quality != "Unknown":
        full_title += f" [{quality}]"
    
    # --- Задаем TITLE ---
    ET.SubElement(item, "title").text = full_title
    
    # --- GUID ---
    guid = ET.SubElement(item, "guid", isPermaLink="false")
    guid.text = f"anilibria-{torrent_id}"
    
    # --- Enclosure ---
    download_url = f"{API_BASE}/anime/torrents/{torrent_id}/file"
    enc = ET.SubElement(item, "enclosure")
    enc.set("url", download_url)
    enc.set("length", str(size_bytes))
    enc.set("type", "application/x-bittorrent")
    
    # --- Link ---
    ET.SubElement(item, "link").text = download_url
    
    # --- Category ---
    ET.SubElement(item, "category").text = "5070"
    
    # --- PubDate ---
    pub_date_str = torrent.get("updated_at") or release.get("updated_at")
    if pub_date_str and isinstance(pub_date_str, str):
        try:
            dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            ET.SubElement(item, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except:
            ET.SubElement(item, "pubDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    else:
        ET.SubElement(item, "pubDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    
    # --- Torznab атрибуты ---
    TORZNAB_NAMESPACE = "http://torznab.com/schemas/2015/feed"
    ET.SubElement(item, f"{{{TORZNAB_NAMESPACE}}}attr", name="seeders", value=str(torrent.get("seeders", 0)))
    ET.SubElement(item, f"{{{TORZNAB_NAMESPACE}}}attr", name="peers", value=str(torrent.get("leechers", 0) + torrent.get("seeders", 0)))
    ET.SubElement(item, f"{{{TORZNAB_NAMESPACE}}}attr", name="category", value="5070")
    
    poster = release.get("poster", {}).get("optimized", {}).get("src")
    if not poster:
        poster = release.get("poster", {}).get("src")
    if poster:
        if poster.startswith("/"):
            poster = "https://anilibria.top" + poster
        ET.SubElement(item, f"{{{TORZNAB_NAMESPACE}}}attr", name="poster", value=poster)
    
    return item

# --- ОСНОВНЫЕ ЭНДПОИНТЫ ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
@app.get("/torznab")
@app.get("/torznab/")
@app.get("/api")
@app.get("/api/")
@app.get("/torznab/api")
@app.get("/torznab/api/")
async def torznab_endpoint(
    t: str = Query("caps"),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    apikey: Optional[str] = Query(None),
    extended: Optional[str] = Query(None)
):
    """Основной эндпоинт для всех torznab запросов."""
    start_time = time.time()
    
    try:
        # --- Обработка caps ---
        if t == "caps":
            root = ET.Element("caps")
            server = ET.SubElement(root, "server")
            ET.SubElement(server, "title").text = "AniLibria"
            ET.SubElement(server, "description").text = "AniLibria Torznab Bridge"
            
            searching = ET.SubElement(root, "searching")
            ET.SubElement(searching, "search", available="yes", supportedParams="q")
            ET.SubElement(searching, "tv-search", available="yes", supportedParams="q,season,ep")
            ET.SubElement(searching, "movie-search", available="yes", supportedParams="q")
            
            categories = ET.SubElement(root, "categories")
            ET.SubElement(categories, "category", id="5000", name="TV")
            ET.SubElement(categories, "category", id="5070", name="Anime")
            
            return Response(content=get_xml_bytes(root), media_type="application/xml")
        
        # --- Обработка поиска и RSS ---
        items_to_process = []
        
        if t in ["search", "tvsearch", "movie", "rss"]:
            if not q:
                # RSS: получаем последние торренты
                print(f"Processing RSS request (limit={limit})")
                latest_torrents = fetch_latest_torrents(limit=min(limit, 100))
                
                if not latest_torrents:
                    print("No torrents found")
                    return Response(content=get_xml_bytes(create_empty_rss()), media_type="application/xml")
                
                # Параллельная загрузка метаданных
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = []
                    for torrent in latest_torrents:
                        release_id = torrent.get('release_id') or torrent.get('release', {}).get('id')
                        if release_id:
                            future = executor.submit(fetch_release_metadata, release_id)
                            futures.append((future, torrent))
                    
                    for future, torrent in futures:
                        try:
                            release = future.result(timeout=20)
                            if release:
                                items_to_process.append((release, torrent))
                        except Exception as e:
                            print(f"Error fetching release: {e}")
            else:
                # Поиск
                print(f"Processing Search request: q='{q}', limit={limit}")
                release_summaries = fetch_releases(query=q, limit=min(limit, 50))
                
                if not release_summaries:
                    print("No releases found")
                    return Response(content=get_xml_bytes(create_empty_rss()), media_type="application/xml")
                
                # Загружаем полные данные с торрентами
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for release_summary in release_summaries[:10]:
                        release_id = release_summary.get("id")
                        if release_id:
                            future = executor.submit(fetch_release_with_torrents, release_id)
                            futures.append(future)
                    
                    for future in futures:
                        try:
                            full_release = future.result(timeout=20)
                            if full_release and 'torrents' in full_release:
                                torrents_list = full_release['torrents']
                                for torrent in torrents_list[:5]:
                                    items_to_process.append((full_release, torrent))
                        except Exception as e:
                            print(f"Error fetching full release: {e}")
        else:
            return Response(content="Unknown functionality", status_code=400)
        
        # --- Создаем RSS ответ ---
        rss = ET.Element(
            "rss",
            attrib={"version": "2.0", "xmlns:torznab": "http://torznab.com/schemas/2015/feed"}
        )
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "AniLibria"
        ET.SubElement(channel, "link").text = "https://anilibria.top"
        ET.SubElement(channel, "description").text = "AniLibria Torznab Feed"
        
        generated_count = 0
        for release, torrent in items_to_process:
            try:
                if not isinstance(torrent, dict):
                    continue
                item = build_rss_item(release, torrent)
                channel.append(item)
                generated_count += 1
            except Exception as e:
                print(f"ERROR building item: {e}")
        
        print(f"Generated {generated_count} XML items in {time.time() - start_time:.2f}s")
        return Response(content=get_xml_bytes(rss), media_type="application/xml")
        
    except Exception as e:
        print(f"ERROR in torznab endpoint: {e}")
        import traceback
        traceback.print_exc()
        return Response(content=f"Error: {str(e)}", status_code=500)

# --- ЗАПУСК (для отладки) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)