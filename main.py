import os
import requests
import adblock
from PySide6.QtCore import QObject, Signal
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo

# רשימות הסינון הרשמיות של uBlock Origin + EasyList
UBLOCK_FILTER_URLS = [
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/filters.txt",
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/privacy.txt",
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/badware.txt",
    "https://easylist.to/easylist/easylist.txt"
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "ublock_green_filters.cache")

RESOURCE_TYPE_MAP = {
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame: "document",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubFrame: "subdocument",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeStylesheet: "stylesheet",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeScript: "script",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage: "image",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeFontResource: "font",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubResource: "other",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeObject: "object",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMedia: "media",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeXhr: "xmlhttprequest",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypePing: "ping",
    QWebEngineUrlRequestInfo.ResourceType.ResourceTypeCspReport: "csp_report",
}


class GreenShieldInterceptor(QWebEngineUrlRequestInterceptor):
    """
    מנוע חסימת פרסומות וסקריפטים ברמת הליבה (מבוסס רשימות uBlock Origin).
    פועל ללא מגבלות Manifest V3 וחוסך סוללה ותעבורת רשת.
    """
    ad_blocked = Signal(int)

    def __init__(self, enabled=True):
        super().__init__()
        self.enabled = enabled
        self.blocked_count = 0
        self.engine = self._build_engine()

    def _load_filter_lists(self) -> list:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached_lines = f.read().splitlines()
            # אם המטמון תקין ומכיל מעל 1000 חוקים, טען אותו מיד
            if len(cached_lines) > 1000:
                return cached_lines

        print("🌿 מוריד את רשימות הסינון הרשמיות של uBlock Origin...")
        all_lines = []
        headers = {"User-Agent": "GreenBrowser/1.0 (AGPL-3.0)"}
        for url in UBLOCK_FILTER_URLS:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    all_lines.extend(resp.text.splitlines())
            except Exception as e:
                print(f"שגיאה בטעינת רשימה {url}: {e}")

        if len(all_lines) > 1000:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(all_lines))
        return all_lines

    def _build_engine(self) -> adblock.Engine:
        lines = self._load_filter_lists()
        filter_set = adblock.FilterSet()
        filter_set.add_filters(lines)
        print(f"🛡️ Green Shield מוכן: נטענו {len(lines)} חוקי סינון של uBlock Origin (ללא מגבלת V3).")
        return adblock.Engine(filter_set)

    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        if not self.enabled:
            return

        url = info.requestUrl().toString()
        if url.startswith("file://") or url.startswith("data:"):
            return

        source_url = info.firstPartyUrl().toString()
        res_type = RESOURCE_TYPE_MAP.get(info.resourceType(), "other")

        result = self.engine.check_network_urls(url, source_url, res_type)
        if result.matched:
            info.block(True)
            self.blocked_count += 1
            self.ad_blocked.emit(self.blocked_count)
