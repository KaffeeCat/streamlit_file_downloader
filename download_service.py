import ipaddress
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, unquote, urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"
MANIFEST_PATH = DOWNLOADS_DIR / "manifest.json"
DEFAULT_PORT = os.environ.get("STREAMLIT_SERVER_PORT", "8501")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

ProgressCallback = Callable[[int, Optional[int]], None]


def _ensure_dirs() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        MANIFEST_PATH.write_text("[]", encoding="utf-8")


def load_manifest() -> list[dict]:
    _ensure_dirs()
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_manifest(entries: list[dict]) -> None:
    _ensure_dirs()
    MANIFEST_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _is_private_host(host: str) -> bool:
    if not host:
        return True

    host = host.lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True

    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        pass

    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    return True
            except ValueError:
                continue
    except socket.gaierror:
        return False

    return False


def validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 http 或 https 链接")
    if not parsed.netloc:
        raise ValueError("URL 格式无效")
    if _is_private_host(parsed.hostname or ""):
        raise ValueError("不允许下载内网或本地地址")
    return url


def _repair_mojibake(name: str) -> str:
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return name


def _filename_from_url_path(url: str) -> str:
    path_name = unquote(urlparse(url).path)
    name = Path(path_name).name
    if name and name not in {"/", ""}:
        return name
    return ""


def _parse_content_disposition_filename(content_disposition: str) -> Optional[str]:
    if not content_disposition:
        return None

    # Prefer RFC 5987 filename*=charset''percent-encoded (handles UTF-8 correctly)
    star_match = re.search(
        r"filename\*\s*=\s*([^;'\"\\s]+)?'([^']*)'([^;]+)",
        content_disposition,
        re.I,
    )
    if star_match:
        charset = (star_match.group(1) or "utf-8").strip().lower()
        encoded_value = star_match.group(3).strip().strip('"')
        try:
            return unquote(encoded_value, encoding=charset)
        except (LookupError, UnicodeDecodeError):
            return unquote(encoded_value, encoding="utf-8")

    quoted_match = re.search(r'filename\s*=\s*"([^"]+)"', content_disposition, re.I)
    if quoted_match:
        return _repair_mojibake(quoted_match.group(1))

    unquoted_match = re.search(r"filename\s*=\s*([^;]+)", content_disposition, re.I)
    if unquoted_match:
        return _repair_mojibake(unquoted_match.group(1).strip().strip('"'))

    return None


def _filename_from_response(url: str, response: requests.Response) -> str:
    cd = response.headers.get("Content-Disposition", "")
    name = _parse_content_disposition_filename(cd)
    if name:
        return name

    url_name = _filename_from_url_path(url)
    if url_name:
        return url_name

    if response.url:
        url_name = _filename_from_url_path(response.url)
        if url_name:
            return url_name

    return "downloaded_file"


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip(". ")
    return name[:200] if name else "downloaded_file"


def build_download_url(stored_name: str, base_url: Optional[str] = None) -> str:
    if PUBLIC_BASE_URL:
        base = PUBLIC_BASE_URL
    elif base_url:
        base = base_url.rstrip("/")
    else:
        base = f"http://localhost:{DEFAULT_PORT}"
    return f"{base}/?dl={quote(stored_name)}"


def get_local_file_path(stored_name: str) -> Path:
    return DOWNLOADS_DIR / stored_name


def _safe_download_path(stored_name: str) -> Optional[Path]:
    if not stored_name or stored_name in {".", ".."} or "/" in stored_name or "\\" in stored_name:
        return None

    file_path = (DOWNLOADS_DIR / stored_name).resolve()
    try:
        file_path.relative_to(DOWNLOADS_DIR.resolve())
    except ValueError:
        return None
    return file_path


def cleanup_orphan_files() -> None:
    """Remove files in downloads/ that are no longer listed in manifest.json."""
    _ensure_dirs()
    entries = load_manifest()
    tracked = {entry.get("stored_name") for entry in entries if entry.get("stored_name")}

    for path in DOWNLOADS_DIR.iterdir():
        if not path.is_file():
            continue
        if path.name in tracked or path.name in {"manifest.json", ".gitkeep"}:
            continue
        path.unlink(missing_ok=True)


def find_entry_by_stored_name(stored_name: str) -> Optional[dict]:
    if not stored_name or "/" in stored_name or "\\" in stored_name:
        return None

    for entry in load_manifest():
        if entry.get("stored_name") == stored_name and entry.get("status") == "success":
            path = DOWNLOADS_DIR / stored_name
            if path.is_file():
                return entry
    return None


def find_existing_entry(source_url: str) -> Optional[dict]:
    for entry in load_manifest():
        if entry.get("source_url") == source_url and entry.get("status") == "success":
            path = DOWNLOADS_DIR / entry.get("stored_name", "")
            if path.is_file():
                return entry
    return None


def download_from_url(
    source_url: str,
    base_url: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    source_url = validate_url(source_url)

    existing = find_existing_entry(source_url)
    if existing:
        existing["download_url"] = build_download_url(existing["stored_name"], base_url)
        if progress_callback:
            progress_callback(existing.get("size_bytes", 0), existing.get("size_bytes", 0))
        return existing

    file_id = uuid.uuid4().hex[:12]
    stored_name = ""
    size_bytes = 0

    with requests.get(
        source_url,
        stream=True,
        timeout=(10, 300),
        headers={"User-Agent": "StreamlitDownloadProxy/1.0"},
        allow_redirects=True,
    ) as response:
        response.raise_for_status()

        if response.url:
            redirect_host = urlparse(response.url).hostname or ""
            if _is_private_host(redirect_host):
                raise ValueError("重定向目标为内网或本地地址，已拒绝")

        content_length_header = response.headers.get("Content-Length")
        total_size = int(content_length_header) if content_length_header else None

        filename = _safe_filename(_filename_from_response(source_url, response))
        stored_name = f"{file_id}_{filename}"
        target_path = DOWNLOADS_DIR / stored_name

        if progress_callback:
            progress_callback(0, total_size)

        with target_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                size_bytes += len(chunk)
                f.write(chunk)
                if progress_callback:
                    progress_callback(size_bytes, total_size)

    entry = {
        "id": file_id,
        "source_url": source_url,
        "filename": filename,
        "stored_name": stored_name,
        "size_bytes": size_bytes,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "download_url": build_download_url(stored_name, base_url),
    }

    entries = load_manifest()
    entries.insert(0, entry)
    save_manifest(entries)
    return entry


def delete_transfer(entry_id: str) -> bool:
    entries = load_manifest()
    target = next((entry for entry in entries if entry.get("id") == entry_id), None)
    if not target:
        return False

    stored_name = target.get("stored_name", "")
    if stored_name:
        file_path = _safe_download_path(stored_name)
        if file_path is None:
            return False
        if file_path.is_file():
            try:
                file_path.unlink()
            except OSError:
                return False
            if file_path.is_file():
                return False

    save_manifest([entry for entry in entries if entry.get("id") != entry_id])
    cleanup_orphan_files()
    return True
