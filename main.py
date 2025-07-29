import sys
import json
import os
from collections import defaultdict
from functools import partial
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
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QDateTime, QTimer

from timer import TimerManager


TIMER_FILE = "timers.json"
CONF_FILE = "conf.json"
ICON_FILE = ""

with open(CONF_FILE, "r", encoding="utf-8") as f:
    ICON_FILE = json.load(f).get("icon_file", "")


class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.timer_manager = TimerManager()
        self.timer_manager.timer_finished.connect(self.on_timer_finished)

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

        self.menu.addSeparator()

        self.action_quit = QAction("❌ 종료", self.menu)
        self.action_quit.triggered.connect(self.app.quit)
        self.menu.addAction(self.action_quit)

        self.tray.setContextMenu(self.menu)

    def trigger_alert(self):
        dialog = TimerInputDialog(self.root)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        if not data["group"]:
            QMessageBox.warning(self.root, "입력 오류", "그룹을 입력하세요.")
            return
        if not data["title"]:
            QMessageBox.warning(self.root, "입력 오류", "제목을 입력하세요.")
            return
        if not data["minutes"].isdigit() or not data["seconds"].isdigit():
            QMessageBox.warning(self.root, "입력 오류", "분과 초는 숫자여야 합니다.")
            return

        group = data["group"]
        title = data["title"]
        minutes = data["minutes"]
        seconds = data["seconds"]

        self.trigger_timer(group, title, minutes, seconds)

    def on_timer_finished(self, group_title_tuple):
        group, title = group_title_tuple
        self.tray.showMessage(
            group, f"{title} 타이머 완료", QSystemTrayIcon.MessageIcon.Information
        )

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_active_timers()

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

    def build_timer_menu(self):
        self.action_saved_timer_menu.clear()

        # JSON 파일 읽기
        if not os.path.exists("timers.json"):
            QMessageBox.warning(self.root, "파일 없음", "timers.json 파일이 없습니다.")
            return

        with open("timers.json", "r", encoding="utf-8") as f:
            all_data = json.load(f)

        for group, timers in sorted(all_data.items()):
            group_menu = QMenu(group, self.action_saved_timer_menu)
            for title, config in sorted(timers.items()):
                action = QAction(title, group_menu)
                action.triggered.connect(
                    partial(
                        self.trigger_timer,
                        group,
                        title,
                        config["minutes"],
                        config["seconds"],
                    )
                )
                group_menu.addAction(action)

            self.action_saved_timer_menu.addMenu(group_menu)

    def trigger_timer(self, group, title, minutes, seconds):
        self.timer_manager.start_timer(group, title, minutes, seconds)
        self.add_timer_to_window(group, title)

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

    def _handle_timer_window_closed(self):
        self.timer_window = None
        self.grid = None
        self.timer_labels = {}

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

        self.grid.addWidget(label_group, self.timer_row_counter, 0)
        self.grid.addWidget(label_title, self.timer_row_counter, 1)
        self.grid.addWidget(label_time, self.timer_row_counter, 2)

        self.timer_labels[(group, title)] = label_time
        self.timer_row_counter += 1

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

        self.grid = grid
        self.timer_row_counter = 1
        self.timer_labels = {}

        self.timer_window.layout().addWidget(scroll)

    def run(self):
        self.app.exec()


class TimerInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("타이머 저장")
        self.setFixedWidth(300)

        self.group_input = QLineEdit()
        self.title_input = QLineEdit()
        self.min_input = QLineEdit()
        self.sec_input = QLineEdit()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("타이머 그룹"))
        layout.addWidget(self.group_input)
        layout.addWidget(QLabel("타이머 제목"))
        layout.addWidget(self.title_input)
        layout.addWidget(QLabel("분"))
        layout.addWidget(self.min_input)
        layout.addWidget(QLabel("초"))
        layout.addWidget(self.sec_input)

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
        }


if __name__ == "__main__":
    app = TrayApp()
    app.run()
