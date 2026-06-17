import os
import shutil
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PyQt5.QtCore import QObject, pyqtSignal

from logger import logger

# 文件去重：同一路径 2 秒内不重复处理
_process_lock = threading.Lock()
_recently_processed = {}  # {normalized_path: timestamp}


def _should_process(file_path):
    """去重：同一文件 3 秒内不重复处理"""
    now = time.time()
    key = os.path.normpath(file_path).lower()
    with _process_lock:
        last = _recently_processed.get(key, 0)
        if now - last < 3:
            return False
        _recently_processed[key] = now
        # 清理超过 30 秒的旧记录
        stale = [k for k, v in _recently_processed.items() if now - v > 30]
        for k in stale:
            del _recently_processed[k]
        return True


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, file_watcher):
        super().__init__()
        self.file_watcher = file_watcher

    def _is_temporary_file(self, file_path):
        if not os.path.exists(file_path):
            return True
        file_name = os.path.basename(file_path)
        _, file_extension = os.path.splitext(file_path)
        file_extension = file_extension.lower()
        return (file_extension in ('.tmp', '.crdownload') or '.tmp' in file_name)

    def on_created(self, event):
        if event.is_directory:
            return
        time.sleep(0.3)
        if self._is_temporary_file(event.src_path):
            logger.debug(f"忽略临时文件: {event.src_path}")
            return
        if not os.path.exists(event.src_path):
            return
        if not _should_process(event.src_path):
            return
        logger.info(f"检测到新文件: {os.path.basename(event.src_path)}")
        self.file_watcher.process_new_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._is_temporary_file(event.dest_path):
            return
        time.sleep(0.3)
        if not os.path.exists(event.dest_path):
            return
        if not _should_process(event.dest_path):
            return
        logger.info(f"检测到重命名/移动文件: {os.path.basename(event.dest_path)}")
        self.file_watcher.process_new_file(event.dest_path)


class FileWatcher(QObject):
    file_classified = pyqtSignal(str, str)

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.observers = []
        self.is_monitoring = False
        self._scan_thread = None
        logger.debug("FileWatcher 实例已创建")

    def start_monitoring(self):
        """启动 watchdog 监听 + 扫描已有文件"""
        if self.is_monitoring:
            logger.debug("已在监听中，跳过")
            return

        config = self.config_manager.get_config()
        source_folders = []
        for key in ('source_folder', 'source_folder_2'):
            path = config.get(key, '')
            if path and os.path.isdir(path):
                source_folders.append(path)

        if not source_folders:
            logger.warning("没有有效的源文件夹")
            return

        # 先启动 watchdog 监听新文件
        self.observers = []
        for folder in source_folders:
            observer = Observer()
            event_handler = FileEventHandler(self)
            observer.schedule(event_handler, folder, recursive=False)
            observer.start()
            self.observers.append(observer)
            logger.info(f"开始监听: {folder}")

        self.is_monitoring = True

        # 单独开线程扫描已有文件（避免阻塞 watchdog）
        self._scan_thread = threading.Thread(target=self._scan_existing_files, args=(source_folders,), daemon=True)
        self._scan_thread.start()

    def _scan_existing_files(self, folders):
        """启动时扫描目录中已有的文件"""
        logger.info("开始扫描已有文件...")
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            try:
                for entry in os.listdir(folder):
                    file_path = os.path.join(folder, entry)
                    if os.path.isfile(file_path):
                        # 跳过临时文件
                        _, ext = os.path.splitext(entry)
                        if ext.lower() in ('.tmp', '.crdownload'):
                            continue
                        if _should_process(file_path):
                            logger.info(f"扫描到已有文件: {entry}")
                            self.process_new_file(file_path)
            except Exception as e:
                logger.error(f"扫描文件夹 {folder} 出错: {str(e)}")
        logger.info("已有文件扫描完成")

    def stop(self):
        for observer in self.observers:
            observer.stop()
        for observer in self.observers:
            observer.join(timeout=5)
        self.observers = []
        self.is_monitoring = False
        logger.info("停止所有监听")

    def _match_rule(self, rule, file_name, file_extension):
        """判断规则是否匹配。返回 (matched, target_folder)"""
        if not rule.get('enabled', True):
            return False, None
        extensions = rule.get('extensions', [])
        if not extensions:
            return False, None
        if file_extension not in [e.lower() for e in extensions]:
            return False, None
        keywords = rule.get('keywords', [])
        if keywords:
            keyword_matched = any(kw.lower() in file_name.lower() for kw in keywords)
            if not keyword_matched:
                return False, None
        return True, rule.get('target_folder', '')

    def process_new_file(self, file_path):
        if not os.path.exists(file_path):
            return

        config = self.config_manager.get_config()
        rules = config.get('rules', [])

        file_name = os.path.basename(file_path)
        _, file_extension = os.path.splitext(file_name)
        file_extension = file_extension.lower()

        if not rules:
            logger.info(f"无匹配规则（规则列表为空），不移动: {file_name}")
            return

        # 遍历规则
        for rule in rules:
            matched, tf = self._match_rule(rule, file_name, file_extension)
            if matched and tf:
                ext_str = ','.join(rule.get('extensions', []))
                kw_str = ','.join(rule.get('keywords', []))
                logger.info(f"匹配规则 [后缀: {ext_str}] [关键词: {kw_str}] → {tf}")
                self._move_file(file_path, tf)
                return

        # 未匹配任何规则：说明原因
        ext_matched_rules = []
        for rule in rules:
            if not rule.get('enabled', True):
                continue
            exts = rule.get('extensions', [])
            if file_extension in [e.lower() for e in exts]:
                ext_matched_rules.append(rule)

        if ext_matched_rules:
            # 后缀匹配但关键词不匹配
            all_keywords = []
            for r in ext_matched_rules:
                all_keywords.extend(r.get('keywords', []))
            logger.info(f"文件 {file_name} 后缀 [{file_extension}] 匹配规则，但关键词 [{', '.join(all_keywords)}] 未命中文件名，不移动")
        else:
            logger.info(f"文件 {file_name} 后缀 [{file_extension}] 未匹配任何规则，不移动")

    def _move_file(self, src_path, target_folder):
        try:
            os.makedirs(target_folder, exist_ok=True)
            file_name = os.path.basename(src_path)
            target_path = os.path.join(target_folder, file_name)

            counter = 1
            name, ext = os.path.splitext(file_name)
            while os.path.exists(target_path):
                target_path = os.path.join(target_folder, f"{name}_{counter}{ext}")
                counter += 1

            shutil.move(src_path, target_path)
            logger.info(f"移动: {os.path.basename(src_path)} -> {target_path}")
            self.file_classified.emit(target_path, target_folder)

        except Exception as e:
            logger.error(f"移动文件失败 {src_path}: {str(e)}")
