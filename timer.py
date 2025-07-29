import os
import json
import pygame
from PyQt6.QtCore import QTimer, QDateTime, QObject, pyqtSignal


TIMER_FILE = "timers.json"
CONF_FILE = "conf.json"
ALARM_PATH = ""

with open(CONF_FILE, "r", encoding="utf-8") as f:
    ALARM_PATH = json.load(f).get("sound_file", "")


class TimerManager(QObject):
    # 타이머 종료 시 (이름, 메시지, 남은 초)
    timer_finished = pyqtSignal(tuple)
    timer_updated = pyqtSignal(tuple, int)  # (이름, 남은 초)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timers = {}  # name: QTimer
        self.ends = {}  # name: QDateTime
        pygame.mixer.init()

    def start_timer(self, group, title, minutes, seconds):
        total_seconds = int(minutes) * 60 + int(seconds)
        if total_seconds <= 0:
            return

        self.stop_timer((group, title))

        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(lambda n=(group, title): self._tick(n))
        timer.start()

        self.timers[(group, title)] = timer
        self.ends[(group, title)] = QDateTime.currentDateTime().addSecs(total_seconds)

    def _tick(self, group_title_tuple):
        group, title = group_title_tuple
        now = QDateTime.currentDateTime()
        end_time = self.ends.get((group, title))
        if not end_time:
            return

        remaining = now.secsTo(end_time)

        if remaining <= 0:
            self._complete((group, title))
        else:
            self.timer_updated.emit((group, title), remaining)

    def _complete(self, group_title_tuple):
        group, title = group_title_tuple
        self.stop_timer((group, title))
        self._play_sound()
        self.timer_finished.emit((group, title))

    def stop_timer(self, group_title_tuple):
        group, title = group_title_tuple
        if (group, title) in self.timers:
            self.timers[(group, title)].stop()
            self.timers[(group, title)].deleteLater()
            del self.timers[(group, title)]
        if (group, title) in self.ends:
            del self.ends[(group, title)]

    def remaining_time(self, group_title_tuple):
        group, title = group_title_tuple
        """남은 시간을 초 단위로 반환 (없으면 None)"""
        if (group, title) in self.ends:
            now = QDateTime.currentDateTime()
            return max(0, now.secsTo(self.ends[(group, title)]))
        return None

    def _play_sound(self):
        try:
            pygame.mixer.music.load(ALARM_PATH)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"[사운드 오류] {e}")

    def load_timers(self):
        if os.path.exists(TIMER_FILE):
            with open(TIMER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_timers(self, timers):
        with open(TIMER_FILE, "w", encoding="utf-8") as f:
            json.dump(timers, f, ensure_ascii=False, indent=2)
