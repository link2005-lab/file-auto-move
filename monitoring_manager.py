import os
import sys
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QThread

from file_watcher import FileWatcher
from logger import logger
from constants import APP_NAME

# 防止重复 setup 的锁
_setup_lock = threading.Lock()


class MonitoringManager(QObject):
    """文件监听管理器"""

    monitoring_status_changed = pyqtSignal(bool)
    file_classified_signal = pyqtSignal(str, str)

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.file_watcher = None
        self.watcher_thread = None
        logger.info("文件监听管理器初始化完成")

    def _has_valid_source_folders(self):
        """检查是否有有效的源文件夹"""
        config = self.config_manager.get_config()
        for key in ('source_folder', 'source_folder_2'):
            path = config.get(key, '')
            if path and os.path.isdir(path):
                return True
        return False

    def setup_file_watcher(self):
        """根据当前配置设置并启动/停止文件监视器（线程安全）"""
        with _setup_lock:
            logger.info("设置文件监视器")
            config = self.config_manager.get_config()
            is_monitoring = config.get('is_monitoring', False)

            # 1. 先完全停止旧的 watcher
            self._stop_watcher_thread()

            if not is_monitoring:
                logger.debug("监听状态为关闭，不启动监视器")
                self.monitoring_status_changed.emit(False)
                return

            if not self._has_valid_source_folders():
                logger.warning("没有有效的源文件夹，无法启动监视器")
                config['is_monitoring'] = False
                self.config_manager.save_config(config)
                self.monitoring_status_changed.emit(False)
                return

            # 2. 创建新的 watcher
            self.file_watcher = FileWatcher(self.config_manager)
            self.file_watcher.file_classified.connect(self.file_classified_signal)

            # 3. 放到独立线程中启动
            self.watcher_thread = QThread()
            self.file_watcher.moveToThread(self.watcher_thread)
            self.watcher_thread.started.connect(self.file_watcher.start_monitoring)

            src1 = config.get('source_folder', '') or '无'
            src2 = config.get('source_folder_2', '') or '无'
            logger.info(f"启动文件监视器线程，监听文件夹: {src1}, {src2}")
            self.watcher_thread.start()
            self.monitoring_status_changed.emit(True)

    def sync_monitoring_state_from_config(self):
        """从配置文件同步监听状态（设置页确定后调用）"""
        logger.info("从配置文件同步监听状态")
        self.setup_file_watcher()

    def _stop_watcher_thread(self):
        """强制停止旧的 watcher 和线程"""
        # 停止 file_watcher 的 observer
        if self.file_watcher:
            try:
                self.file_watcher.stop()
            except Exception as e:
                logger.error(f"停止 file_watcher 出错: {e}")
            self.file_watcher.file_classified.disconnect()
            self.file_watcher = None

        # 停止并等待线程退出
        if self.watcher_thread:
            try:
                if self.watcher_thread.isRunning():
                    self.watcher_thread.quit()
                    if not self.watcher_thread.wait(3000):
                        logger.warning("watcher 线程未能正常退出，强制终止")
                        self.watcher_thread.terminate()
                        self.watcher_thread.wait(2000)
            except Exception as e:
                logger.error(f"停止 watcher_thread 出错: {e}")
            self.watcher_thread = None

    def start_monitoring(self):
        return self._set_monitoring_state(True)

    def stop_monitoring(self):
        return self._set_monitoring_state(False)

    def toggle_monitoring(self):
        config = self.config_manager.get_config()
        return self._set_monitoring_state(not config.get('is_monitoring', False))

    def exit(self):
        """退出时清理"""
        self._stop_watcher_thread()
        self.monitoring_status_changed.emit(False)
        return True

    def _set_monitoring_state(self, enable):
        action = "开始" if enable else "停止"
        logger.info(f"{action}监听")

        config = self.config_manager.get_config()

        if enable and not self._has_valid_source_folders():
            logger.warning("未设置有效的源文件夹，无法开始监听")
            return False

        if config.get('is_monitoring', False) == enable:
            logger.debug(f"当前已经是{action}状态，无需操作")
            return True

        config['is_monitoring'] = enable
        self.config_manager.save_config(config)

        self.setup_file_watcher()
        return True

    def get_monitoring_status(self):
        return self.config_manager.get_config().get('is_monitoring', False)
