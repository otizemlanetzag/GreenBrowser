import os
import sys
import urllib.parse
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTabWidget, QSplitter, QLabel
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile

from battery_guard import TabBatteryGuard
from green_shield import GreenShieldInterceptor

NEWTAB_URL = QUrl.fromLocalFile(os.path.abspath("newtab.html"))

ECO_DARK_GREEN_QSS = """
QMainWindow, QWidget {
    background-color: #0b140e;
    color: #d8f3dc;
    font-family: "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #1b4332;
    background-color: #080f0a;
}
QTabBar::tab {
    background-color: #132418;
    color: #95d5b2;
    padding: 7px 14px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #1b4332;
    color: #ffffff;
    font-weight: bold;
    border-bottom: 2px solid #52b788;
}
QLineEdit {
    background-color: #132418;
    color: #e8f5e9;
    border: 1px solid #2d6a4f;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus {
    border: 1px solid #52b788;
}
QPushButton {
    background-color: #1b4332;
    color: #d8f3dc;
    border: 1px solid #2d6a4f;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #2d6a4f;
}
"""

TRUST_REGISTRY = {
    "eco.trust": "https://www.ecosia.org",
    "codeberg.trust": "https://codeberg.org"
}


class GreenBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Green Browser (AGPL-3.0)")
        self.resize(1360, 820)

        self.battery_guard = TabBatteryGuard(max_battery_drain_percent_per_hour=5.0)

        self.shield = GreenShieldInterceptor(enabled=True)
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self.shield)

        nav_bar = QHBoxLayout()

        self.back_btn = QPushButton("◀")
        self.forward_btn = QPushButton("▶")
        self.reload_btn = QPushButton("↻")
        self.home_btn = QPushButton("🏠")
        self.new_tab_btn = QPushButton("+ Tab")

        self.trust_badge = QLabel("🌿 Eco")
        self.trust_badge.setStyleSheet("color: #74c69d; font-weight: bold; padding: 0 6px;")

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Search with Ecosia or enter URL (including .trust)...")
        self.url_input.returnPressed.connect(self.navigate_current_tab)

        self.shield_btn = QPushButton("🛡️ Blocked: 0")
        self.shield_btn.setToolTip("Green Shield (uBlock Origin rules) - Click to toggle")
        self.shield_btn.clicked.connect(self.toggle_shield)
        self.shield.ad_blocked.connect(lambda count: self.shield_btn.setText(f"🛡️ Blocked: {count}"))

        self.ai_toggle_btn = QPushButton("🤖 Ecosia AI: OFF")
        self.ai_toggle_btn.clicked.connect(self.toggle_ecosia_ai)

        nav_bar.addWidget(self.back_btn)
        nav_bar.addWidget(self.forward_btn)
        nav_bar.addWidget(self.reload_btn)
        nav_bar.addWidget(self.home_btn)
        nav_bar.addWidget(self.new_tab_btn)
        nav_bar.addWidget(self.trust_badge)
        nav_bar.addWidget(self.url_input)
        nav_bar.addWidget(self.shield_btn)
        nav_bar.addWidget(self.ai_toggle_btn)

        self.splitter = QSplitter(Qt.Horizontal)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.ai_sidebar_container = QWidget()
        self.ai_sidebar_container.setMinimumWidth(340)
        self.ai_sidebar_container.setMaximumWidth(450)
        self.ai_sidebar_layout = QVBoxLayout(self.ai_sidebar_container)
        self.ai_sidebar_layout.setContentsMargins(4, 4, 4, 4)

        ai_top_bar = QHBoxLayout()
        ai_label = QLabel("🌿 Ecosia AI Chat")
        ai_label.setStyleSheet("font-weight: bold; color: #95d5b2;")
        kill_ai_btn = QPushButton("✖ Kill & Free RAM")
        kill_ai_btn.setStyleSheet("background-color: #3d1c1c; border-color: #6b2c2c;")
        kill_ai_btn.clicked.connect(self.toggle_ecosia_ai)

        ai_top_bar.addWidget(ai_label)
        ai_top_bar.addWidget(kill_ai_btn)
        self.ai_sidebar_layout.addLayout(ai_top_bar)

        self.ai_webview = None
        self.ai_sidebar_container.hide()

        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.ai_sidebar_container)

        self.back_btn.clicked.connect(lambda: self.current_browser().back() if self.current_browser() else None)
        self.forward_btn.clicked.connect(lambda: self.current_browser().forward() if self.current_browser() else None)
        self.reload_btn.clicked.connect(lambda: self.current_browser().reload() if self.current_browser() else None)
        self.home_btn.clicked.connect(lambda: self._load_url_in_browser(self.current_browser(), "green://newtab") if self.current_browser() else None)
        self.new_tab_btn.clicked.connect(lambda: self.add_new_tab("green://newtab"))

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.addLayout(nav_bar)
        main_layout.addWidget(self.splitter)
        self.setCentralWidget(central)

        self.add_new_tab("green://newtab")

    def add_new_tab(self, url_str: str = "green://newtab"):
        browser = QWebEngineView()
        self.battery_guard.register_tab(browser.page())

        index = self.tabs.addTab(browser, "New Tab")
        self.tabs.setCurrentIndex(index)

        browser.titleChanged.connect(lambda title, b=browser: self.tabs.setTabText(self.tabs.indexOf(b), title[:22] or "New Tab"))
        browser.urlChanged.connect(lambda qurl, b=browser: self._sync_url_bar(qurl, b))

        self._load_url_in_browser(browser, url_str)

    def close_tab(self, index: int):
        if self.tabs.count() <= 1:
            return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()

    def current_browser(self) -> QWebEngineView:
        return self.tabs.currentWidget()

    def navigate_current_tab(self):
        browser = self.current_browser()
        if browser:
            self._load_url_in_browser(browser, self.url_input.text().strip())

    def _load_url_in_browser(self, browser: QWebEngineView, raw_input: str):
        if not raw_input:
            return

        if raw_input == "green://newtab":
            browser.setProperty("trust_domain", None)
            browser.setUrl(NEWTAB_URL)
            self.url_input.clear()
            return

        clean_host = raw_input.replace("https://", "").replace("http://", "").split("/")[0]


        if clean_host.endswith(".trust"):
            if clean_host in TRUST_REGISTRY:
                target = TRUST_REGISTRY[clean_host]
                browser.setProperty("trust_domain", clean_host)
                browser.setUrl(QUrl(target))
            else:
                html = f"""
                <body style="background:#080f0a; color:#d8f3dc; font-family:sans-serif; text-align:center; padding-top:100px;">
                    <h2>🛡️ Unverified .TRUST Domain</h2>
                    <p>The domain <b>{clean_host}</b> has not been manually audited under AGPL-3.0-or-later.</p>
                </body>
                """
                browser.setHtml(html)
            return

        browser.setProperty("trust_domain", None)
        if "." not in raw_input or " " in raw_input:
            encoded_query = urllib.parse.quote_plus(raw_input)
            url = f"https://www.ecosia.org/search/?q={encoded_query}"
        elif not raw_input.startswith(("http://", "https://")):
            url = f"https://{raw_input}"
        else:
            url = raw_input

        browser.setUrl(QUrl(url))

    def _sync_url_bar(self, qurl: QUrl, browser: QWebEngineView):
        if qurl.host().endswith(".trust"):
            self._load_url_in_browser(browser, qurl.host())
            return

        if browser != self.current_browser():
            return

        if qurl == NEWTAB_URL:
            self.url_input.clear()
            self.trust_badge.setText("🌿 New Tab")
            self.trust_badge.setStyleSheet("color: #74c69d; padding: 0 6px;")
            return

        trust_domain = browser.property("trust_domain")
        if trust_domain:
            self.url_input.setText(trust_domain)
            self.trust_badge.setText("🛡️ .TRUST (AGPL)")
            self.trust_badge.setStyleSheet("color: #52b788; font-weight: bold; padding: 0 6px;")
        else:
            self.url_input.setText(qurl.toString())
            self.trust_badge.setText("🌿 Eco")
            self.trust_badge.setStyleSheet("color: #74c69d; padding: 0 6px;")

    def on_tab_changed(self, index: int):
        browser = self.current_browser()
        if browser:
            self._sync_url_bar(browser.url(), browser)

    def toggle_shield(self):
        self.shield.enabled = not self.shield.enabled
        if self.shield.enabled:
            self.shield_btn.setText(f"🛡️ Blocked: {self.shield.blocked_count}")
            self.shield_btn.setStyleSheet("")
        else:
            self.shield_btn.setText("⚠️ Shield OFF")
            self.shield_btn.setStyleSheet("background-color: #3d1c1c; border-color: #6b2c2c;")
        if self.current_browser():
            self.current_browser().reload()

    def toggle_ecosia_ai(self):
        if self.ai_webview is None:
            self.ai_webview = QWebEngineView()
            self.ai_webview.setUrl(QUrl("https://www.ecosia.org/ai-chat/"))
            self.ai_sidebar_layout.addWidget(self.ai_webview)
            self.ai_sidebar_container.show()
            self.ai_toggle_btn.setText("🤖 Ecosia AI: ON")
            self.ai_toggle_btn.setStyleSheet("background-color: #2d6a4f; color: #ffffff; font-weight: bold;")
        else:
            self.ai_sidebar_layout.removeWidget(self.ai_webview)
            self.ai_webview.deleteLater()
            self.ai_webview = None
            self.ai_sidebar_container.hide()
            self.ai_toggle_btn.setText("🤖 Ecosia AI: OFF")
            self.ai_toggle_btn.setStyleSheet("")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ECO_DARK_GREEN_QSS)
    window = GreenBrowser()
    window.show()
    sys.exit(app.exec())
