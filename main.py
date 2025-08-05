import sys
import json
import os
import keyboard
from collections import defaultdict
from functools import partial

import pygame
from PyQt6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QWidget,
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
    QScrollArea,
    QGridLayout,
)
from PyQt6.QtGui import QIcon, QAction, QFont, QFontDatabase
from PyQt6.QtCore import Qt, QDateTime, QTimer, QObject, pyqtSignal

from timer import TimerManager


TIMER_FILE = "timers.json"
CONF_FILE = "conf.json"
ICON_FILE = ""
FONT_FILE = ""
FONT_SIZE = 9
ALERT_SOUND_FILE = ""
ALERT_VOLUME = 0.5

with open(CONF_FILE, "r", encoding="utf-8") as f:
    json_data = json.load(f)
    ICON_FILE = json_data.get("icon_file", "")
    FONT_FILE = json_data.get("font_file", "")
    FONT_SIZE = json_data.get("font_size", 9)
    ALERT_SOUND_FILE = json_data.get("alert_sound_file", "")
    ALERT_VOLUME = json_data.get("alert_volume", 0.5)


class TrayApp:
    def __init__(self):
        pygame.mixer.init()
        self.app = QApplication(sys.argv)
        self.timer_manager = TimerManager()
        self.timer_manager.timer_finished.connect(self.on_timer_finished)
        self.hotkey_list = []
        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.hotkey_triggered.connect(self.on_hotkey_triggered)

        # 숨겨진 루트 위젯 (필수: 이벤트 루프 안정화)
        self.root = QWidget()
        self.root.hide()

        # 트레이 아이콘 설정
        self.tray = QSystemTrayIcon()
        self.icon = QIcon(ICON_FILE)
        self.tray.setIcon(self.icon)
        self.tray.setToolTip("트레이 타이머")
        self.tray.setVisible(True)

        # 트레이 클릭 이벤트 추가
        self.tray.activated.connect(self.on_tray_activated)
        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(1000)  # 1초마다 갱신
        self.refresh_timer.timeout.connect(self.update_timer_window)
        self.refresh_timer.stop()

        # 메뉴 구성
        self.menu = QMenu(self.root)

        self.action_trigger_alert = QAction("📣 단발성 알림 추가", self.menu)
        self.action_trigger_alert.triggered.connect(
            partial(
                self.trigger_alert,
            )
        )
        self.menu.addAction(self.action_trigger_alert)

        self.action_save_timer = QAction("➕ 타이머 저장", self.menu)
        self.action_save_timer.triggered.connect(self.save_timer)
        self.menu.addAction(self.action_save_timer)

        self.action_saved_timer_menu = QMenu("📋 저장된 타이머", self.menu)
        self.build_timer_menu()
        self.menu.addMenu(self.action_saved_timer_menu)

        self.action_delete_timer = QAction("🗑 타이머 삭제", self.menu)
        self.action_delete_timer.triggered.connect(self.show_delete_dialog)
        self.menu.addAction(self.action_delete_timer)

        self.menu.addSeparator()

        self.action_quit = QAction("❌ 종료", self.menu)
        self.action_quit.triggered.connect(self.app.quit)
        self.menu.addAction(self.action_quit)

        self.tray.setContextMenu(self.menu)

    def run(self):
        self.app.exec()

    # 메뉴 빌드
    def build_timer_menu(self):
        self.action_saved_timer_menu.clear()
        for hotkey in self.hotkey_list:
            keyboard.remove_hotkey(hotkey)

        # JSON 파일 읽기
        if not os.path.exists(TIMER_FILE):
            QMessageBox.warning(self.root, "파일 없음", "TIMER_FILE 파일이 없습니다.")
            return

        with open(TIMER_FILE, "r", encoding="utf-8") as f:
            all_data = json.load(f)

        for group, timers in sorted(all_data.items()):
            group_menu = QMenu(group, self.action_saved_timer_menu)
            for title, config in sorted(timers.items()):
                action = QAction(title, group_menu)
                common_args = (group, title, config["minutes"], config["seconds"])
                action.triggered.connect(partial(self.trigger_timer, *common_args))
                if config.get("hotkey", None):
                    keyboard.add_hotkey(
                        config["hotkey"],
                        partial(self.on_hotkey, *common_args),
                    )
                    self.hotkey_list.append(config["hotkey"])
                group_menu.addAction(action)

            self.action_saved_timer_menu.addMenu(group_menu)

    def _rebuild_timer_window_contents(self):
        for i in reversed(range(self.timer_window.layout().count())):
            widget = self.timer_window.layout().itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # 새로 스크롤 + 그리드 구성
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        grid = QGridLayout()
        container.setLayout(grid)
        scroll.setWidget(container)

        grid.addWidget(QLabel("<b>그룹</b>"), 0, 0)
        grid.addWidget(QLabel("<b>제목</b>"), 0, 1)
        grid.addWidget(QLabel("<b>남은 시간</b>"), 0, 2)
        grid.addWidget(QLabel("<b>삭제</b>"), 0, 3)

        self.grid = grid
        self.timer_row_counter = 1
        self.timer_labels = {}

        self.timer_window.layout().addWidget(scroll)

    # 타이머 동작
    def trigger_timer(self, group, title, minutes, seconds):
        self.timer_manager.start_timer(group, title, minutes, seconds)
        self.add_timer_to_window(group, title)

    def on_timer_finished(self, group_title_tuple):
        group, title = group_title_tuple
        self.alert = FloatingAlert(group, title, mode="finished")
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.alert.width() - 20
        y = screen.height() - self.alert.height() - 60
        self.alert.move(x, y)
        try:
            pygame.mixer.music.load(ALERT_SOUND_FILE)
            pygame.mixer.music.set_volume(ALERT_VOLUME)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"[사운드 오류] {e}")
        self.alert.show()

    def on_hotkey(self, group, title, minutes, seconds):
        self.hotkey_bridge.hotkey_triggered.emit(group, title, minutes, seconds)

    def on_hotkey_triggered(self, group, title, minutes, seconds):
        self.alert = FloatingAlert(group, title, mode="hotkey_start")
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.alert.width() - 20
        y = screen.height() - self.alert.height() - 60
        self.alert.move(x, y)
        self.trigger_timer(group, title, minutes, seconds)
        self.alert.show()

    # 타이머 저장 / 알림 추가
    def save_timer(self):
        dialog = TimerInputDialog(self.root)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        # 유효성 검사
        if not data["group"]:
            QMessageBox.warning(self.root, "입력 오류", "그룹을 입력하세요.")
            return
        if not data["title"]:
            QMessageBox.warning(self.root, "입력 오류", "제목을 입력하세요.")
            return
        if not data["minutes"].isdigit() or not data["seconds"].isdigit():
            QMessageBox.warning(self.root, "입력 오류", "분과 초는 숫자여야 합니다.")
            return
        if data["hotkey"]:
            try:
                keyboard.parse_hotkey(data["hotkey"])
            except Exception as e:
                QMessageBox.warning(self.root, "입력 오류", "잘못된 핫키 입력입니다.")
                return

        group = data["group"]
        title = data["title"]
        timers = {}

        if os.path.exists(TIMER_FILE):
            with open(TIMER_FILE, "r", encoding="utf-8") as f:
                timers = json.load(f)

        timers = defaultdict(dict, timers)
        timers[group][data["title"]] = {
            "minutes": int(data["minutes"]),
            "seconds": int(data["seconds"]),
        }
        if data.get("hotkey"):
            if data["hotkey"] in self.hotkey_list:
                QMessageBox.warning(
                    self.root,
                    "입력 오류",
                    f"중복된 핫키 입력입니다: {group}/{title}",
                )
                return
            timers[group][title]["hotkey"] = data["hotkey"]

        sorted_timers = {}
        for group_key, timer_dict in sorted(timers.items()):
            sorted_timers[group_key] = {
                title: config for title, config in sorted(timer_dict.items())
            }
        timers = sorted_timers

        with open(TIMER_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(timers), f, ensure_ascii=False, indent=2)

        self.build_timer_menu()

        QMessageBox.information(
            self.root, "저장 완료", f"'{group} > {title}' 타이머가 저장되었습니다!"
        )

    def trigger_alert(self):
        dialog = TimerInputDialog(self.root)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        if data["minutes"] == "":
            data["minutes"] = "0"
        if data["seconds"] == "":
            data["seconds"] = "0"

        if not data["group"]:
            QMessageBox.warning(self.root, "입력 오류", "그룹을 입력하세요.")
            return
        if not data["title"]:
            QMessageBox.warning(self.root, "입력 오류", "제목을 입력하세요.")
            return
        if not data["minutes"].isdigit() or not data["seconds"].isdigit():
            QMessageBox.warning(self.root, "입력 오류", "분과 초는 숫자여야 합니다.")
            return
        if data["hotkey"]:
            QMessageBox.warning(
                self.root, "입력 오류", "단발성 알림은 단축키 지원이 되지 않습니다."
            )
            return

        group = data["group"]
        title = data["title"]
        minutes = data["minutes"]
        seconds = data["seconds"]

        self.trigger_timer(group, title, minutes, seconds)

    def delete_active_timer(self, group, title, row_number):
        # 1. 타이머 정지
        self.timer_manager.stop_timer((group, title))

        # 2. 타이머 창 UI에서 제거
        label = self.timer_labels.pop((group, title), None)
        if label:
            label.deleteLater()

        # 3. 레이아웃에서 나머지 그룹/제목 라벨도 제거
        for col in range(4):
            item = self.grid.itemAtPosition(row_number, col)
            if item and item.widget():
                item.widget().deleteLater()

        print(f"[삭제됨] 실행 중인 타이머: {group} / {title}")

    # 쇼윈도
    def show_active_timers(self):
        if hasattr(self, "timer_window") and self.timer_window is not None:
            # 이미 창이 열려 있으면 포커스만 줌
            self.timer_window.activateWindow()
            return

        self.timer_window = QDialog(self.root)
        self.timer_window.setWindowTitle("⏱ 현재 실행 중인 타이머")
        self.timer_window.resize(300, 150)

        # 전체 레이아웃
        outer_layout = QVBoxLayout()

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.grid = QGridLayout()
        container.setLayout(self.grid)
        container.setMinimumHeight(70)
        scroll.setWidget(container)

        # 헤더
        self.grid.addWidget(QLabel("<b>그룹</b>"), 0, 0)
        self.grid.addWidget(QLabel("<b>제목</b>"), 0, 1)
        self.grid.addWidget(QLabel("<b>남은 시간</b>"), 0, 2)
        self.grid.addWidget(QLabel("<b>삭제</b>"), 0, 3)

        self.timer_labels = {}  # (group, title): QLabel 매핑

        now = QDateTime.currentDateTime()
        self.timer_row_counter = 1

        for (group, title), end_time in self.timer_manager.ends.items():
            remaining = now.secsTo(end_time)
            if remaining <= 0:
                continue

            self.grid.addWidget(QLabel(group), self.timer_row_counter, 0)
            self.grid.addWidget(QLabel(title), self.timer_row_counter, 1)

            label = QLabel()
            self.timer_labels[(group, title)] = label
            self.grid.addWidget(label, self.timer_row_counter, 2)
            
            del_btn = QPushButton("🗑")
            del_btn.setFixedWidth(30)
            del_btn.clicked.connect(partial(self.delete_active_timer, group, title, self.timer_row_counter))
            self.grid.addWidget(del_btn, self.timer_row_counter, 3)

            self.timer_row_counter += 1

        if self.timer_row_counter == 1:
            outer_layout.addWidget(QLabel("⛔ 현재 실행 중인 타이머가 없습니다."))
        else:
            outer_layout.addWidget(scroll)

        self.update_timer_window()

        self.timer_window.setLayout(outer_layout)
        self.timer_window.show()

        self.timer_window.finished.connect(self._handle_timer_window_closed)

        # QTimer로 실시간 갱신 시작
        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.update_timer_window)
        self.refresh_timer.start()

    def add_timer_to_window(self, group, title):
        # 타이머 상태창이 떠 있을 때만 처리
        if not hasattr(self, "timer_window") or self.timer_window is None:
            return
        if (
            not hasattr(self, "grid")
            or self.grid is None
            or not self.timer_window.findChild(QGridLayout)
        ):
            self._rebuild_timer_window_contents()
        if (group, title) in self.timer_labels:
            return  # 이미 표시 중이면 무시

        label_group = QLabel(group)
        label_title = QLabel(title)
        label_time = QLabel("계산 중...")
        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(30)
        del_btn.clicked.connect(partial(self.delete_active_timer, group, title, self.timer_row_counter))

        self.grid.addWidget(label_group, self.timer_row_counter, 0)
        self.grid.addWidget(label_title, self.timer_row_counter, 1)
        self.grid.addWidget(label_time, self.timer_row_counter, 2)
        self.grid.addWidget(del_btn, self.timer_row_counter, 3)

        self.timer_labels[(group, title)] = label_time
        self.timer_row_counter += 1

    def update_timer_window(self):
        now = QDateTime.currentDateTime()

        for (group, title), label in self.timer_labels.items():
            end_time = self.timer_manager.ends.get((group, title), None)
            if not end_time:
                label.setText(f"종료됨")
                continue

            remaining = now.secsTo(end_time)
            if remaining <= 0:
                label.setText(f"종료됨")
            else:
                m, s = divmod(remaining, 60)
                label.setText(f"{m}분 {s}초 남음")

    def show_delete_dialog(self):
        dialog = TimerDeleteDialog(self)
        dialog.exec()
        self.build_timer_menu()  # 삭제 후 메뉴 다시 빌드

    # 이벤트 핸들러
    def _handle_timer_window_closed(self):
        self.timer_window = None
        self.grid = None
        self.timer_labels = {}

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_active_timers()


class TimerInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("타이머 저장")
        self.setFixedWidth(300)

        self.group_input = QLineEdit()
        self.title_input = QLineEdit()
        self.min_input = QLineEdit()
        self.sec_input = QLineEdit()
        self.hotkey_input = QLineEdit()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("타이머 그룹"))
        layout.addWidget(self.group_input)
        layout.addWidget(QLabel("타이머 제목"))
        layout.addWidget(self.title_input)
        layout.addWidget(QLabel("분"))
        layout.addWidget(self.min_input)
        layout.addWidget(QLabel("초"))
        layout.addWidget(self.sec_input)
        layout.addWidget(QLabel("단축키 (예: ctrl+alt+1)"))
        layout.addWidget(self.hotkey_input)

        button_layout = QHBoxLayout()
        save_btn = QPushButton("저장")
        cancel_btn = QPushButton("취소")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def get_data(self):
        return {
            "group": self.group_input.text().strip(),
            "title": self.title_input.text().strip(),
            "minutes": self.min_input.text().strip(),
            "seconds": self.sec_input.text().strip(),
            "hotkey": self.hotkey_input.text().strip(),
        }


class HotkeyBridge(QObject):
    hotkey_triggered = pyqtSignal(str, str, int, int)


class FloatingAlert(QWidget):
    def __init__(self, group, title, mode="finished", parent=None):
        super().__init__(parent)
        self.styel_sheet = """
            background-color: white;
            border: 2px solid black;
            border-radius: 4px;
        """
        self.setStyleSheet(self.styel_sheet)
        font_id = QFontDatabase.addApplicationFont(FONT_FILE)
        font_family = QFontDatabase.applicationFontFamilies(font_id)
        if font_family:
            self.custom_font = font_family[0]
        else:
            self.custom_font = "Malgun Gothic"

        if mode == "finished":
            self.finish_alert(group, title)
        elif mode == "hotkey_start":
            self.hotkey_start_alert(group, title)

    def hotkey_start_alert(self, group, title):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 80)

        self.label = QLabel(f"{group}: {title}\n시작했습니다", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont(self.custom_font, FONT_SIZE))
        self.label.setGeometry(10, 10, 200, 60)
        self.label.setStyleSheet("color: black;")

        QTimer.singleShot(3000, self.close)  # 3초 후 자동 닫힘

    def finish_alert(self, group, title):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 80)

        now = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.label = QLabel(f"{group}: {title} 완료\n{now}", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont(self.custom_font, FONT_SIZE))
        self.label.setGeometry(10, 10, 200, 60)
        self.label.setStyleSheet("color: black;")

        QTimer.singleShot(10000, self.close)  # 10초 후 자동 닫힘

    def mousePressEvent(self, event):
        self.close()  # 클릭하면 창 닫기


class TimerDeleteDialog(QDialog):
    def __init__(self, tray_app: TrayApp):
        super().__init__(tray_app.root)
        self.setWindowTitle("🗑 타이머 삭제")
        self.setMinimumWidth(400)
        self.tray_app = tray_app

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        container = QWidget()
        self.grid = QGridLayout()
        container.setLayout(self.grid)
        self.scroll.setWidget(container)

        self.grid.addWidget(QLabel("<b>그룹</b>"), 0, 0)
        self.grid.addWidget(QLabel("<b>제목</b>"), 0, 1)
        self.grid.addWidget(QLabel("<b>삭제</b>"), 0, 2)

        self.timers = self._load_timers()
        self._populate_grid()

    def _load_timers(self):
        if not os.path.exists(TIMER_FILE):
            return {}
        with open(TIMER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _populate_grid(self):
        row = 1
        for group, titles in self.timers.items():
            for title in titles:
                self.grid.addWidget(QLabel(group), row, 0)
                self.grid.addWidget(QLabel(title), row, 1)
                del_btn = QPushButton("삭제")
                del_btn.clicked.connect(partial(self.delete_timer, group, title))
                self.grid.addWidget(del_btn, row, 2)
                row += 1

    def delete_timer(self, group, title):
        confirm = QMessageBox.question(
            self,
            "확인",
            f"'{group} > {title}' 타이머를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.tray_app.hotkey_list.remove(self.timers[group][title]["hotkey"])
            del self.timers[group][title]
            if not self.timers[group]:
                del self.timers[group]

            with open(TIMER_FILE, "w", encoding="utf-8") as f:
                json.dump(self.timers, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "삭제 완료", f"{group} > {title} 삭제됨")
            self._refresh_ui()

    def _refresh_ui(self):
        # 기존 grid 위젯들 제거
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        # 헤더 다시 추가
        self.grid.addWidget(QLabel("<b>그룹</b>"), 0, 0)
        self.grid.addWidget(QLabel("<b>제목</b>"), 0, 1)
        self.grid.addWidget(QLabel("<b>삭제</b>"), 0, 2)

        # 현재 타이머 목록 기준으로 다시 표시
        row = 1
        for group, titles in self.timers.items():
            for title in titles:
                self.grid.addWidget(QLabel(group), row, 0)
                self.grid.addWidget(QLabel(title), row, 1)
                del_btn = QPushButton("삭제")
                del_btn.clicked.connect(partial(self.delete_timer, group, title))
                self.grid.addWidget(del_btn, row, 2)
                row += 1


if __name__ == "__main__":
    app = TrayApp()
    app.run()
