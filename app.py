from typing import Optional
import html
import os
import textwrap
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import requests

from download_service import (
    DEFAULT_PORT,
    MANIFEST_PATH,
    PUBLIC_BASE_URL,
    build_download_url,
    build_static_download_path,
    download_from_url,
    delete_transfer,
    get_local_file_path,
    load_manifest,
    cleanup_orphan_files,
)


APP_NAME = "Streamlit File Downloader"
APP_TAGLINE = "File Proxy Gateway"
AUTHOR_NAME = "KaffeeCat"
AUTHOR_URL = os.environ.get("AUTHOR_URL", "https://github.com/KaffeeCat").rstrip("/")
SHOW_VISITOR_COUNTER = os.environ.get("SHOW_VISITOR_COUNTER", "true").lower() in {
    "1",
    "true",
    "yes",
}
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "G-EQYBHFSMPW").strip()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_server_location() -> dict:
    """获取运行本应用的服务器公网 IP 与地理位置信息。"""
    response = requests.get(
        "http://ip-api.com/json/?fields=status,message,query,country,countryCode,"
        "regionName,city,lat,lon,timezone,isp",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "success":
        raise RuntimeError(data.get("message", "无法获取位置信息"))

    return data


@st.cache_data(show_spinner=False)
def load_manifest_cached(manifest_mtime: float) -> list:
    return load_manifest()


def get_app_base_url() -> str:
    """根据当前访问地址生成基础 URL，避免链接指向不可达的公网 IP。"""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL

    try:
        headers = st.context.headers
        if headers:
            host = headers.get("Host")
            proto = headers.get("X-Forwarded-Proto", "http")
            if host:
                return f"{proto}://{host}"
    except Exception:
        pass

    return f"http://localhost:{DEFAULT_PORT}"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _render_html(content: str) -> None:
    """Render HTML without Markdown treating indented lines as code blocks."""
    cleaned = textwrap.dedent(content).strip()
    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def _card_open(extra_style: str = "") -> str:
    return (
        f'<div style="background:rgba(128,128,128,0.08);border:1px solid rgba(128,128,128,0.22);'
        f'border-radius:12px;padding:1.15rem 1.25rem;margin-bottom:1rem;{extra_style}">'
    )


CARD_CLOSE = "</div>"


def _meta_chip(text: str) -> str:
    safe = html.escape(text)
    return (
        f'<span style="display:inline-block;padding:0.2rem 0.55rem;margin-right:0.4rem;'
        f'border-radius:999px;background:rgba(128,128,128,0.14);font-size:0.78rem;'
        f'font-weight:500;color:inherit;">{safe}</span>'
    )


def render_page_header() -> None:
    _render_html(
        f"""
        {_card_open("margin-bottom:1.25rem;")}
        <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                    letter-spacing:0.12em;color:rgba(128,128,128,0.95);margin-bottom:0.35rem;">
            {APP_TAGLINE}
        </div>
        <div style="font-size:1.85rem;font-weight:700;line-height:1.2;margin-bottom:0.45rem;">
            {APP_NAME}
        </div>
        <div style="font-size:0.95rem;line-height:1.55;color:rgba(128,128,128,0.95);max-width:42rem;">
            Pull files from any public URL to this server, then distribute them via
            fast local download links. All successful transfers are tracked below.
        </div>
        {CARD_CLOSE}
        """
    )


def inject_app_styles() -> None:
    _render_html(
        """
        <style>
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.62rem 1rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.88rem;
            letter-spacing: 0.02em;
            text-decoration: none;
            text-align: center;
            cursor: pointer;
            border: none;
            transition: all 0.15s ease;
            box-sizing: border-box;
            line-height: 1.2;
        }
        .btn-primary {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: white !important;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
        }
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
        }
        .btn-block {
            display: flex;
            width: 100%;
            margin-top: 0.85rem;
        }
        .btn-action {
            display: inline-flex;
            width: auto;
            min-height: 32px;
            padding: 0.38rem 0.85rem;
            font-size: 0.8rem;
        }
        div[data-testid="stHorizontalBlock"]:has(button[title="Remove file"]) {
            margin-top: 0.75rem;
            align-items: center;
        }
        .ext-badge {
            flex-shrink: 0;
            width: 2.6rem;
            height: 2.6rem;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(37, 99, 235, 0.15);
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            color: #2563eb;
        }
        .file-title {
            font-size: 1rem;
            font-weight: 600;
            word-break: break-word;
            line-height: 1.35;
            margin-bottom: 0.35rem;
        }
        .field-label {
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: rgba(128, 128, 128, 0.95);
            margin: 0.75rem 0 0.25rem;
        }
        .field-value {
            font-size: 0.82rem;
            word-break: break-all;
            color: rgba(128, 128, 128, 0.95);
        }
        .share-box {
            font-family: ui-monospace, monospace;
            font-size: 0.8rem;
            word-break: break-all;
            padding: 0.55rem 0.65rem;
            border-radius: 8px;
            background: rgba(128, 128, 128, 0.12);
        }
        div[data-testid="stHorizontalBlock"]:has(button[title="Remove file"])
            div[data-testid="stButton"]:has(button[title="Remove file"]) > button {
            min-height: 32px !important;
            height: 32px !important;
            width: 32px !important;
            min-width: 32px !important;
            padding: 0 !important;
            margin: 0 !important;
            font-size: 0.95rem !important;
            font-weight: 400 !important;
            line-height: 1 !important;
            border-radius: 7px !important;
            border: 1px solid rgba(128, 128, 128, 0.22) !important;
            background: rgba(128, 128, 128, 0.08) !important;
            color: rgba(128, 128, 128, 0.72) !important;
            box-shadow: none !important;
        }
        div[data-testid="stHorizontalBlock"]:has(button[title="Remove file"])
            div[data-testid="stButton"]:has(button[title="Remove file"]) > button:hover {
            background: rgba(239, 68, 68, 0.1) !important;
            border-color: rgba(239, 68, 68, 0.32) !important;
            color: #ef4444 !important;
        }
        section.main div[data-testid="stFormSubmitButton"] > button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            min-height: 42px !important;
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
            border: none !important;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25) !important;
        }
        section.main div[data-testid="stFormSubmitButton"] > button:hover {
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35) !important;
        }
        </style>
        """
    )


def _download_button_html(entry: dict, *, label: str = "Download", compact: bool = False) -> str:
    file_path = get_local_file_path(entry["stored_name"])
    if not file_path.is_file():
        return ""

    download_path = build_static_download_path(entry["stored_name"])
    display_name = html.escape(entry.get("filename", entry["stored_name"]))
    safe_label = html.escape(label)
    btn_class = "btn btn-primary btn-action" if compact else "btn btn-primary btn-block"

    return (
        f'<a class="{btn_class}" href="{download_path}" '
        f'download="{display_name}">{safe_label}</a>'
    )


@st.dialog("Confirm Removal")
def confirm_delete_dialog(entry: dict) -> None:
    filename = entry.get("filename", "this file")
    st.markdown(f"**{html.escape(filename)}**")
    st.caption("The file will be deleted from this server. This cannot be undone.")

    col_remove, col_cancel = st.columns(2)
    with col_remove:
        if st.button(
            "Remove",
            type="primary",
            use_container_width=True,
            key=f"dlg_remove_{entry['id']}",
        ):
            if delete_transfer(entry["id"]):
                load_manifest_cached.clear()
                st.toast(f"Removed {filename}", icon="🗑️")
            else:
                st.toast("Delete failed", icon="⚠️")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", use_container_width=True, key=f"dlg_cancel_{entry['id']}"):
            st.rerun()


def render_history_item(entry: dict, base_url: str) -> None:
    filename = entry.get("filename", "Unknown file")
    safe_filename = html.escape(filename)
    safe_source = html.escape(entry.get("source_url", "-"))
    download_url = build_download_url(f"downloads/{entry['stored_name']}", base_url)
    safe_download_url = html.escape(download_url)
    size_text = format_size(entry.get("size_bytes", 0))
    downloaded_at = entry.get("downloaded_at", "-")[:19].replace("T", " ") + " UTC"
    ext = html.escape(filename.rsplit(".", 1)[-1].upper()[:6] if "." in filename else "FILE")

    with st.container(border=True):
        _render_html(
            f"""
            <div style="display:flex;align-items:flex-start;gap:0.85rem;">
                <div class="ext-badge">{ext}</div>
                <div style="flex:1;min-width:0;">
                    <div class="file-title">{safe_filename}</div>
                    <div>{_meta_chip(size_text)}{_meta_chip(downloaded_at)}</div>
                </div>
            </div>
            <div class="field-label">Source URL</div>
            <div class="field-value">{safe_source}</div>
            <div class="field-label">Share Link</div>
            <div class="share-box">{safe_download_url}</div>
            """
        )

        download_col, delete_col = st.columns([1, 0.07], gap="small")
        with download_col:
            _render_html(_download_button_html(entry, compact=True))
        with delete_col:
            if st.button("🗑", key=f"del_{entry['id']}", help="Remove file", use_container_width=True):
                confirm_delete_dialog(entry)


def render_history_summary(entries: list) -> None:
    total_bytes = sum(e.get("size_bytes", 0) for e in entries)
    _render_html(
        f"""
        <div style="display:flex;align-items:center;justify-content:space-between;
                    margin:1.5rem 0 0.85rem;gap:1rem;flex-wrap:wrap;">
            <div>
                <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                            letter-spacing:0.1em;color:rgba(128,128,128,0.95);margin-bottom:0.25rem;">
                    Download Archive
                </div>
                <div style="font-size:1.35rem;font-weight:700;">Transfer History</div>
            </div>
            <div style="text-align:right;">
                {_meta_chip(f"{len(entries)} files")}
                {_meta_chip(format_size(total_bytes) + " total")}
            </div>
        </div>
        """
    )


@st.fragment
def render_transfer_history(base_url: str) -> None:
    manifest_mtime = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.exists() else 0.0
    entries = [e for e in load_manifest_cached(manifest_mtime) if e.get("status") == "success"]

    if not entries:
        _render_html(
            f"""
            {_card_open("margin-top:1.25rem;text-align:center;")}
            <div style="font-size:2rem;margin-bottom:0.5rem;">📂</div>
            <div style="font-size:1rem;font-weight:600;margin-bottom:0.35rem;">No transfers yet</div>
            <div style="font-size:0.88rem;color:rgba(128,128,128,0.95);">
                Submit a URL above to start building your download archive.
            </div>
            {CARD_CLOSE}
            """
        )
        return

    render_history_summary(entries)
    for entry in entries:
        render_history_item(entry, base_url)


def render_server_profile(info: dict) -> None:
    location_parts = [p for p in [info.get("city"), info.get("regionName")] if p]
    location_detail = ", ".join(location_parts) if location_parts else "—"

    lat = info.get("lat")
    lon = info.get("lon")
    coords = f"{lat:.4f}, {lon:.4f}" if lat is not None and lon is not None else "—"

    rows = [
        ("Country", f"{info['country']} ({info['countryCode']})"),
        ("Region", info.get("regionName") or "—"),
        ("City", info.get("city") or "—"),
        ("Timezone", info.get("timezone") or "—"),
        ("Coordinates", coords),
        ("ISP", info.get("isp") or "—"),
    ]
    rows_html = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:0.75rem;'
        f'padding:0.4rem 0;border-bottom:1px solid rgba(128,128,128,0.15);">'
        f'<span style="color:rgba(128,128,128,0.95);font-size:0.78rem;'
        f'text-transform:uppercase;letter-spacing:0.04em;flex-shrink:0;">{html.escape(label)}</span>'
        f'<span style="font-size:0.85rem;font-weight:500;text-align:right;word-break:break-word;">'
        f'{html.escape(str(value))}</span></div>'
        for label, value in rows
    )

    _render_html(
        f"""
        <div style="background:rgba(128,128,128,0.08);border:1px solid rgba(128,128,128,0.22);
                    border-radius:12px;padding:1rem 1rem 0.65rem;margin-bottom:0.75rem;">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        letter-spacing:0.1em;color:rgba(128,128,128,0.95);margin-bottom:0.45rem;">
                Public Endpoint
            </div>
            <div style="font-size:1.2rem;font-weight:700;font-family:ui-monospace,monospace;
                        line-height:1.3;margin-bottom:0.35rem;">
                {html.escape(info["query"])}
            </div>
            <div style="font-size:0.92rem;font-weight:500;margin-bottom:0.9rem;">
                {html.escape(location_detail)}
            </div>
            {rows_html}
        </div>
        """
    )


def patch_streamlit_index_html(ga_id: str) -> None:
    """将 GA 代码写入 Streamlit 的 index.html <head>，供 Google 安装检测识别。"""
    marker = f"<!-- ga4:{ga_id} -->"
    index_path = Path(st.__file__).parent / "static" / "index.html"

    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError:
        return

    if marker in content:
        return

    ga_block = (
        f"{marker}\n"
        "<!-- Google tag (gtag.js) -->\n"
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>\n'
        '<script id="ga-gtag-config">\n'
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{ga_id}');\n"
        "</script>\n"
    )

    if "</head>" not in content:
        return

    try:
        index_path.write_text(content.replace("</head>", f"{ga_block}</head>", 1), encoding="utf-8")
    except OSError:
        return


def inject_google_analytics_runtime(ga_id: str) -> None:
    """在主页面的 <head> 中注入 GA（Streamlit Cloud 上 index.html 可能不可写时的备用方案）。"""
    if st.session_state.get("_ga_runtime_injected"):
        return

    st.session_state._ga_runtime_injected = True
    safe_ga_id = html.escape(ga_id, quote=True)
    runtime_script = f"""
    <script>
    (function () {{
        var doc = document;
        try {{
            if (window.parent && window.parent.document && window.parent.document.head) {{
                doc = window.parent.document;
            }}
        }} catch (e) {{}}

        if (doc.getElementById("ga-gtag-config")) return;

        var loader = doc.createElement("script");
        loader.async = true;
        loader.src = "https://www.googletagmanager.com/gtag/js?id={safe_ga_id}";
        doc.head.appendChild(loader);

        var config = doc.createElement("script");
        config.id = "ga-gtag-config";
        config.text =
            "window.dataLayer = window.dataLayer || [];"
            + "function gtag(){{dataLayer.push(arguments);}}"
            + "gtag('js', new Date());"
            + "gtag('config', '{safe_ga_id}');";
        doc.head.appendChild(config);
    }})();
    </script>
    """

    if hasattr(st, "html"):
        try:
            st.html(runtime_script, unsafe_allow_javascript=True)
            return
        except TypeError:
            st.html(runtime_script)
            return

    components.html(runtime_script, height=0, scrolling=False)


def inject_analytics() -> None:
    """通过环境变量注入第三方统计脚本（数据保存在对应平台，不在本机记录）。"""
    if GA_MEASUREMENT_ID:
        inject_google_analytics_runtime(GA_MEASUREMENT_ID)

    snippets: list[str] = []

    goatcounter = os.environ.get("GOATCOUNTER_CODE", "").strip()
    if goatcounter:
        safe_code = html.escape(goatcounter)
        snippets.append(
            f'<script data-goatcounter="https://{safe_code}.goatcounter.com/count" '
            f'async src="//gc.zgo.at/count.js"></script>'
        )

    cf_token = os.environ.get("CLOUDFLARE_ANALYTICS_TOKEN", "").strip()
    if cf_token:
        safe_token = html.escape(cf_token)
        snippets.append(
            "<script defer src='https://static.cloudflareinsights.com/beacon.min.js' "
            f"data-cf-beacon='{{\"token\": \"{safe_token}\"}}'></script>"
        )

    if snippets:
        components.html("\n".join(snippets), height=0, scrolling=False)


def render_sidebar_footer() -> None:
    safe_author = html.escape(AUTHOR_NAME)
    safe_author_url = html.escape(AUTHOR_URL, quote=True)

    _render_html(
        f"""
        <div style="margin-top:1.25rem;padding-top:1rem;border-top:1px solid rgba(128,128,128,0.2);">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        letter-spacing:0.1em;color:rgba(128,128,128,0.95);margin-bottom:0.45rem;">
                About
            </div>
            <div style="font-size:0.88rem;line-height:1.5;color:rgba(128,128,128,0.95);">
                Built by
                <a href="{safe_author_url}" target="_blank" rel="noopener noreferrer"
                   style="color:#2563eb;font-weight:600;text-decoration:none;">
                    {safe_author}
                </a>
            </div>
        </div>
        """
    )

    if SHOW_VISITOR_COUNTER:
        components.html(
            """
            <div style="margin-top:0.85rem;font-size:0.78rem;line-height:1.55;
                        color:rgba(128,128,128,0.95);">
                <div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;
                            letter-spacing:0.08em;margin-bottom:0.35rem;">
                    Site Traffic
                </div>
                <div>Total visits · <span id="busuanzi_value_site_pv">—</span></div>
                <div>Unique visitors · <span id="busuanzi_value_site_uv">—</span></div>
            </div>
            <script async src="https://busuanzi.ibruogart.com/busuanzi/2.3/busuanzi.pure.mini.js"></script>
            """,
            height=78,
            scrolling=False,
        )


def render_sidebar_header() -> None:
    _render_html(
        """
        <div style="margin-bottom:1rem;">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        letter-spacing:0.1em;color:rgba(128,128,128,0.95);margin-bottom:0.3rem;">
                Host Overview
            </div>
            <div style="font-size:1.35rem;font-weight:700;line-height:1.25;margin-bottom:0.35rem;">
                Server Location
            </div>
            <div style="font-size:0.85rem;line-height:1.45;color:rgba(128,128,128,0.95);">
                IP address and geographic region of this machine.
            </div>
        </div>
        """
    )


def render_sidebar() -> None:
    with st.sidebar:
        render_sidebar_header()

        try:
            info = fetch_server_location()
            render_server_profile(info)

            if info.get("lat") is not None and info.get("lon") is not None:
                st.map([{"lat": info["lat"], "lon": info["lon"]}])

        except requests.RequestException as e:
            st.error(f"网络请求失败：{e}")
        except RuntimeError as e:
            st.error(str(e))

        render_sidebar_footer()


def render_download_section(base_url: str) -> None:
    render_page_header()

    _render_html(
        """
        <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                    letter-spacing:0.1em;color:rgba(128,128,128,0.95);margin-bottom:0.65rem;">
            New Transfer
        </div>
        """
    )

    with st.container(border=True):
        with st.form("url_download_form", clear_on_submit=False):
            file_url = st.text_input(
                "Remote File URL",
                placeholder="https://example.com/releases/app-installer.dmg",
                help="Enter a public http or https URL. The file will be fetched and cached on this server.",
            )
            submitted = st.form_submit_button(
                "Fetch to Server",
                type="primary",
                use_container_width=True,
            )

    feedback = st.empty()

    if submitted:
        feedback.empty()
        if not file_url.strip():
            feedback.warning("Please enter a file URL.")
        else:
            progress_bar = st.progress(0, text="Initializing transfer...")
            try:
                def update_progress(downloaded: int, total: Optional[int]) -> None:
                    if total and total > 0:
                        ratio = min(downloaded / total, 1.0)
                        progress_bar.progress(
                            ratio,
                            text=(
                                f"Downloaded {format_size(downloaded)} / {format_size(total)} "
                                f"({ratio * 100:.1f}%)"
                            ),
                        )
                    else:
                        progress_bar.progress(
                            0,
                            text=f"Downloaded {format_size(downloaded)} (total size unknown)",
                        )

                entry = download_from_url(file_url, base_url, progress_callback=update_progress)
                load_manifest_cached.clear()
                progress_bar.progress(
                    1.0,
                    text=f"Complete · {format_size(entry['size_bytes'])}",
                )
                feedback.success("✓ Transfer Complete")
            except ValueError as e:
                progress_bar.empty()
                feedback.error(str(e))
            except requests.RequestException as e:
                progress_bar.empty()
                feedback.error(f"Transfer failed: {e}")
    else:
        feedback.empty()

    render_transfer_history(base_url)


if GA_MEASUREMENT_ID:
    patch_streamlit_index_html(GA_MEASUREMENT_ID)

st.set_page_config(
    page_title=APP_NAME,
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_app_styles()
inject_analytics()
cleanup_orphan_files()
render_sidebar()
render_download_section(get_app_base_url())
