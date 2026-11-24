import os
import requests
import adblock
from PySide6.QtCore import QObject, Signal
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo

# רשימות הסינון הרשמיות של uBlock Origin + EasyList
UBLOCK_FILTER_URLS = [
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://easylist.to"
]

CACHE_FILE = "ublock_green_filters.cache"

# מיפוי סוגי המשאבים של QtWebEngine לשמות שמנוע adblock מכיר
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
    ad_blocked = Signal(int)  # משדר את סך הבקשות שנחסמו

    def __init__(self, enabled=True):
        super().__init__()
        self.enabled = enabled
        self.blocked_count = 0
        self.engine = self._build_engine()

    def _load_filter_lists(self) -> list[str]:
        # אם קיים קובץ מטמון מקומי, טען אותו מיד (0 צריכת רשת וסוללה בהפעלה)
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return f.read().splitlines()

        print("🌿 מוריד לראשונה את רשימות הסינון הרשמיות של uBlock Origin...")
        all_lines = []
        for url in UBLOCK_FILTER_URLS:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    all_lines.extend(resp.text.splitlines())
            except Exception as e:
                print(f"שגיאה בטעינת רשימה {url}: {e}")

        if all_lines:
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
        # אל תחסום קבצים מקומיים של הדפדפן (כמו newtab.html)
        if url.startswith("file://") or url.startswith("data:"):
            return

        source_url = info.firstPartyUrl().toString()
        res_type = RESOURCE_TYPE_MAP.get(info.resourceType(), "other")

        # בדיקה במיקרו-שניות במנוע Rust
        result = self.engine.check_network_urls(url, source_url, res_type)
        if result.matched:
            info.block(True)
            self.blocked_count += 1
            self.ad_blocked.emit(self.blocked_count)
