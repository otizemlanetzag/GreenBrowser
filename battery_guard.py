import time
import psutil
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage


class TabBatteryGuard(QObject):
    """
    מנגנון הגנת סוללה אקטיבי פר-טאב (רישיון: AGPL-3.0-or-later).
    מודד צריכת אנרגיה משוקללת לכל טאב בנפרד, מקפיא טאבים חורגים
    ומבקש אישור חד-פעמי בלבד מהמשתמש (ללא שמירת 'אשר תמיד').
    """
    tab_frozen = Signal(str, float)  # (כותרת האתר, אחוז צריכת סוללה מוערך לשעה)

    def __init__(self, max_battery_drain_percent_per_hour=5.0, check_interval_ms=3000):
        super().__init__()
        # סף המקסימום המותר לאתר בודד (X% סוללה לשעה)
        self.threshold_percent = max_battery_drain_percent_per_hour
        self.check_interval_ms = check_interval_ms

        # מעקב אחר טאבים: { page_id: {"page": QWebEnginePage, "temp_allowed_until": float, "high_usage_strikes": int} }
        self.monitored_tabs = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._scan_all_tabs)
        self.timer.start(self.check_interval_ms)

    def register_tab(self, page: QWebEnginePage):
        """רישום טאב חדש למעקב אנרגיה"""
        page_id = id(page)
        self.monitored_tabs[page_id] = {
            "page": page,
            "temp_allowed_until": 0.0,  # אישור זמני לסשן הנוכחי בלבד (אין 'אשר תמיד')
            "high_usage_strikes": 0
        }
        page.destroyed.connect(lambda: self.unregister_tab(page_id))

    def unregister_tab(self, page_id: int):
        self.monitored_tabs.pop(page_id, None)

    def _estimate_battery_drain_per_hour(self, pid: int) -> float:
        """
        חישוב הערכת צריכת סוללה לשעה (%) עבור תהליך של טאב ספציפי.
        משקלל את ניצול ה-CPU של התהליך מול קיבולת הסוללה הנוכחית.
        """
        if not pid:
            return 0.0
        try:
            proc = psutil.Process(pid)
            # מדידת אחוז ניצול מעבד של תהליך הטאב (מנורמל למספר הליבות)
            cpu_percent = proc.cpu_percent(interval=None) / psutil.cpu_count(logical=True)
            
            # שקלול בסיסי: ניצול מלא של CPU בלפטופ ממוצע צורך כ-25%-35% סוללה בשעה
            estimated_hourly_drain = (cpu_percent / 100.0) * 30.0
            return round(estimated_hourly_drain, 2)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0

    def _scan_all_tabs(self):
        now = time.time()
        battery = psutil.sensors_battery()

        # אם המחשב מחובר לחשמל, אפשר להחליט אם להקל בסף או לאכוף בכל מצב (כאן נאכף תמיד לחיסכון אקולוגי)
        is_on_battery = battery.power_plugged is False if battery else True

        for page_id, data in list(self.monitored_tabs.items()):
            page: QWebEnginePage = data["page"]

            # אם הטאב כבר מוקפא או קיבל אישור חד-פעמי שעדיין בתוקף (למשל ל-10 דקות הקרובות)
            if page.lifecycleState() == QWebEnginePage.LifecycleState.Frozen:
                continue
            if now < data["temp_allowed_until"]:
                continue

            pid = page.renderProcessPid()
            drain_rate = self._estimate_battery_drain_per_hour(pid)

            if drain_rate > self.threshold_percent:
                data["high_usage_strikes"] += 1
                # דורש 2 בדיקות רצופות (6 שניות) כדי לא להקפיא סתם בגלל טעינה ראשונית של עמוד
                if data["high_usage_strikes"] >= 2:
                    self._freeze_and_prompt(page, data, drain_rate)
            else:
                data["high_usage_strikes"] = max(0, data["high_usage_strikes"] - 1)

    def _freeze_and_prompt(self, page: QWebEnginePage, data: dict, drain_rate: float):
        """הקפאה מיידית של הטאב ובקשת אישור חד-פעמי (ללא אפשרות 'אשר תמיד')"""
        # 1. הקפאת הטאב מיד כדי לעצור את זלילת הסוללה
        page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        site_title = page.title() or page.url().host() or "אתר לא ידוע"
        self.tab_frozen.emit(site_title, drain_rate)

        # 2. הצגת חלונית אישור למשתמש — ללא כפתור 'אשר תמיד'
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("🌿 הגנת סוללה ירוקה (Green Battery Guard)")
        msg_box.setText(
            f"האתר '{site_title}' צורך אנרגיה גבוהה מהמותר.\n"
            f"צריכה מוערכת: {drain_rate}% סוללה לשעה (הסף שהוגדר: {self.threshold_percent}%).\n\n"
            "הטאב הוקפא אוטומטית כדי לחסוך באנרגיה. האם לאשר המשך פעילות?"
        )

        allow_once_btn = msg_box.addButton("אשר הפעם (ל-10 דקות)", QMessageBox.AcceptRole)
        keep_frozen_btn = msg_box.addButton("השאר מוקפא (חסוך סוללה)", QMessageBox.RejectRole)
        msg_box.setDefaultButton(keep_frozen_btn)

        msg_box.exec()

        if msg_box.clickedButton() == allow_once_btn:
            # הפשרת הטאב והענקת אישור זמני ל-10 דקות בלבד (ללא שמירה לדיסק)
            data["temp_allowed_until"] = time.time() + 600
            data["high_usage_strikes"] = 0
            page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
