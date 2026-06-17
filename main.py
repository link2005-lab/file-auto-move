import sys
import os
import socket
import ctypes
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox, QStyle
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer

from config_manager import ConfigManager
from settings_dialog import SettingsDialog
from notification_handler import NotificationHandler
from logger import logger
from monitoring_manager import MonitoringManager
from constants import APP_NAME
from startup_manager import update_startup_status, is_in_startup

# 单实例：socket 端口绑定（进程退出自动释放）
_lock_socket = None
_LOCK_PORT = 45678


def is_already_running():
    """检查是否已有实例在运行（socket 端口绑定方式）"""
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(('127.0.0.1', _LOCK_PORT))
        return False
    except socket.error:
        return True


class FileClassifierApp(QObject):
    def __init__(self):
        super().__init__()

        logger.info(f"{APP_NAME} 启动")

        try:
            myappid = APP_NAME
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.warning(f"无法设置 App User Model ID: {e}")

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.config_manager = ConfigManager()
        self.notification_handler = NotificationHandler()
        self.monitoring_manager = MonitoringManager(self.config_manager)

        self._settings_dialog = None
        self._click_timer = None

        self._setup_signals()
        self._sync_auto_start()
        self._setup_tray()

        self.monitoring_manager.setup_file_watcher()
        self._update_tray_icon_color()
        logger.info("初始化完成")

    def _setup_signals(self):
        self.monitoring_manager.monitoring_status_changed.connect(self._on_monitoring_changed)
        self.monitoring_manager.file_classified_signal.connect(self.on_file_classified)

    def _sync_auto_start(self):
        config = self.config_manager.get_config()
        cfg_start = config.get('auto_start', False)
        actual_start = is_in_startup()
        if cfg_start != actual_start:
            if cfg_start:
                if not update_startup_status(True):
                    config['auto_start'] = False
                    self.config_manager.save_config(config)
            else:
                config['auto_start'] = actual_start
                self.config_manager.save_config(config)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setToolTip(APP_NAME)

        # 打包后 icon.png 在 sys._MEIPASS 临时解压目录
        if getattr(sys, 'frozen', False):
            icon_dir = sys._MEIPASS
        else:
            icon_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(icon_dir, 'icon.png')

        self._original_icon = QIcon(icon_path) if os.path.exists(icon_path) else self.app.style().standardIcon(QStyle.SP_FileIcon)
        self._gray_icon = self._make_gray_icon(self._original_icon)

        self.tray_icon.setIcon(self._original_icon)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.messageClicked.connect(self.on_notification_clicked)

        self._create_menu()
        self.tray_icon.show()
        self.update_menu_state()

    def _make_gray_icon(self, icon):
        """生成灰色图标（停止状态）"""
        pixmap = icon.pixmap(32, 32, QIcon.Normal, QIcon.On)
        if pixmap.isNull():
            return icon
        gray = QPixmap(pixmap.size())
        gray.fill(Qt.transparent)
        painter = QPainter(gray)
        painter.setOpacity(0.35)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return QIcon(gray)

    def _update_tray_icon_color(self):
        """根据监听状态切换图标颜色"""
        is_monitoring = self.monitoring_manager.get_monitoring_status()
        self.tray_icon.setIcon(self._original_icon if is_monitoring else self._gray_icon)
        status_text = "监听中" if is_monitoring else "已暂停"
        self.tray_icon.setToolTip(f"{APP_NAME} ({status_text})")

    def _on_monitoring_changed(self, enabled):
        """监听状态变化时更新图标"""
        self._update_tray_icon_color()
        self.update_menu_state()

    def _create_menu(self):
        self.tray_menu = QMenu()

        self.open_classify_action = QAction('打开分类文件夹', self)
        self.open_classify_action.triggered.connect(self.open_target_folder)
        self.tray_menu.addAction(self.open_classify_action)

        self.open_monitor_action = QAction('打开监听文件夹', self)
        self.open_monitor_action.triggered.connect(self.open_source_folder)
        self.tray_menu.addAction(self.open_monitor_action)

        self.tray_menu.addSeparator()

        self.settings_action = QAction('设置', self)
        self.settings_action.triggered.connect(self.open_folder_settings)
        self.tray_menu.addAction(self.settings_action)

        self.log_action = QAction('查看日志', self)
        self.log_action.triggered.connect(self.open_log_file)
        self.tray_menu.addAction(self.log_action)

        self.tray_menu.addSeparator()

        self.exit_action = QAction('退出', self)
        self.exit_action.triggered.connect(self.exit_app)
        self.tray_menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)

    def open_path(self, path):
        if not path:
            return
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                return
        logger.info(f"打开路径: {path}")
        if sys.platform == 'win32':
            os.startfile(path)

    def open_log_file(self):
        from constants import LOG_FILE
        # 打包后日志在 exe 同目录
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'log')
        else:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
        log_path = os.path.join(log_dir, LOG_FILE)
        if os.path.exists(log_path):
            self.open_path(log_path)
        else:
            QMessageBox.information(None, APP_NAME, '日志文件尚未生成')

    def open_folder_settings(self):
        # 如果设置窗口已打开，只把它提到最前
        if self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        self._settings_dialog = SettingsDialog(self.config_manager, self.monitoring_manager)
        if self._settings_dialog.exec_():
            # 确定后，根据最新的 is_monitoring 状态重新 setup
            self.monitoring_manager.sync_monitoring_state_from_config()
            self._update_tray_icon_color()
            self.update_menu_state()
        self._settings_dialog = None

    def open_source_folder(self):
        config = self.config_manager.get_config()
        src = config.get('source_folder', '')
        if src:
            self.open_path(src)

    def open_target_folder(self):
        config = self.config_manager.get_config()
        rules = config.get('rules', [])
        if rules and rules[0].get('target_folder'):
            self.open_path(rules[0].get('target_folder'))

    def update_menu_state(self):
        is_monitoring = self.monitoring_manager.get_monitoring_status()

    def on_file_classified(self, file_path, target_folder):
        logger.info(f"收到文件分类信号: {file_path} -> {target_folder}")
        self.notification_handler.store_classified_file_info(file_path, target_folder)
        config = self.config_manager.get_config()
        if config.get('show_notifications', True):
            self.tray_icon.showMessage(
                "分类成功",
                f"文件 {os.path.basename(file_path)} 已移动",
                QSystemTrayIcon.Information,
                2000
            )

    def on_notification_clicked(self):
        self.notification_handler.open_folder_and_select_file()

    def on_tray_icon_activated(self, reason):
        # Windows 下：双击会先触发两次 Trigger，再触发 DoubleClick
        # 用 QTimer 延迟处理单击，若收到 DoubleClick 则取消
        if reason == QSystemTrayIcon.DoubleClick:
            logger.info("托盘图标双击，打开设置")
            # 取消待处理的单击
            if self._click_timer is not None:
                try:
                    self._click_timer.stop()
                except Exception:
                    pass
            self.open_folder_settings()
            return

        if reason == QSystemTrayIcon.Trigger:
            # 延迟 350ms 再执行单击逻辑，若期间收到 DoubleClick 则 timer 被 stop
            if self._click_timer is not None:
                try:
                    self._click_timer.stop()
                except Exception:
                    pass
            self._click_timer = QTimer()
            self._click_timer.setSingleShot(True)
            self._click_timer.timeout.connect(self._on_single_click)
            self._click_timer.start(350)

    def _on_single_click(self):
        """单击托盘图标：切换监听状态"""
        logger.info("托盘图标单击，切换监听状态")
        self.monitoring_manager.toggle_monitoring()

    def exit_app(self):
        self.monitoring_manager.exit()
        self.tray_icon.hide()
        # 释放 socket 端口
        global _lock_socket
        if _lock_socket:
            _lock_socket.close()
            _lock_socket = None
        self.app.quit()


def main():
    app = QApplication(sys.argv)

    if is_already_running():
        QMessageBox.warning(None, APP_NAME, f"{APP_NAME} 已经在运行中。")
        sys.exit(1)

    app_instance = FileClassifierApp()
    sys.exit(app_instance.app.exec_())


if __name__ == '__main__':
    main()
