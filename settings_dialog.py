import os
import json
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QCheckBox, QFileDialog, QMessageBox,
                             QGroupBox, QWidget, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from constants import APP_NAME, LOG_FILE
from startup_manager import update_startup_status, is_in_startup
from monitoring_manager import MonitoringManager


class SettingsDialog(QDialog):
    def __init__(self, config_manager, monitoring_manager=None):
        super().__init__()
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.config_manager = config_manager
        self.config = self.config_manager.get_config()

        if monitoring_manager is None:
            raise ValueError("MonitoringManager instance is required.")
        self.monitoring_manager = monitoring_manager

        # 连接监听状态变化信号，同步复选框
        self.monitoring_manager.monitoring_status_changed.connect(self._on_monitoring_changed)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.init_ui()

    # ==================== 信号处理 ====================

    def _on_monitoring_changed(self, enabled):
        """外部切换监听状态时同步复选框"""
        if hasattr(self, 'monitoring_checkbox') and self.monitoring_checkbox.isChecked() != enabled:
            self.monitoring_checkbox.setChecked(enabled)

    # ==================== UI 初始化 ====================

    def init_ui(self):
        self.setWindowTitle('文件自动分类器')
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        main_layout = QVBoxLayout()

        self.tab_widget = QTabWidget()

        self.basic_tab = QWidget()
        self.init_basic_tab()
        self.tab_widget.addTab(self.basic_tab, "基本设置")

        self.rules_tab = QWidget()
        self.init_rules_tab()
        self.tab_widget.addTab(self.rules_tab, "规则设置")

        main_layout.addWidget(self.tab_widget)

        # 底部按钮栏：日志(左) ··· 取消 确定(右)
        btn_layout = QHBoxLayout()

        self.log_btn = QPushButton("日志")
        self.log_btn.setToolTip("打开日志文件查看操作记录")
        self.log_btn.clicked.connect(self._open_log_file)
        btn_layout.addWidget(self.log_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def _open_log_file(self):
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log', LOG_FILE)
        if os.path.exists(log_path):
            os.startfile(log_path)
        else:
            QMessageBox.information(self, '文件自动分类器', "日志文件尚未生成")

    # ==================== 基本设置 Tab ====================

    def init_basic_tab(self):
        layout = QVBoxLayout()

        # 监听文件夹区域（两个文件夹放在同一个组里）
        source_group = QGroupBox('监听文件夹')
        source_layout = QVBoxLayout()
        source_layout.setSpacing(4)

        # 监听文件夹 1
        row1 = QHBoxLayout()
        self.source_folder_edit = QLineEdit(self.config.get('source_folder', ''))
        self.source_folder_edit.setReadOnly(True)
        browse_source1_btn = QPushButton('浏览...')
        browse_source1_btn.clicked.connect(self.browse_source_folder)
        row1.addWidget(self.source_folder_edit)
        row1.addWidget(browse_source1_btn)
        source_layout.addLayout(row1)

        # 监听文件夹 2（无额外文字标签）
        row2 = QHBoxLayout()
        self.source_folder2_edit = QLineEdit(self.config.get('source_folder_2', ''))
        self.source_folder2_edit.setReadOnly(True)
        browse_source2_btn = QPushButton('浏览...')
        browse_source2_btn.clicked.connect(self.browse_source_folder_2)
        row2.addWidget(self.source_folder2_edit)
        row2.addWidget(browse_source2_btn)
        source_layout.addLayout(row2)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # 三个选项同行显示
        options_group = QGroupBox('其他设置')
        options_layout = QHBoxLayout()

        actual_auto_start = is_in_startup()
        if self.config.get('auto_start', False) != actual_auto_start:
            self.config['auto_start'] = actual_auto_start
            self.config_manager.save_config(self.config)

        self.auto_start_checkbox = QCheckBox('开机启动')
        self.auto_start_checkbox.setChecked(self.config.get('auto_start', False))

        self.show_notifications_checkbox = QCheckBox('显示通知')
        self.show_notifications_checkbox.setChecked(self.config.get('show_notifications', True))

        self.monitoring_checkbox = QCheckBox('开启监听')
        self.monitoring_checkbox.setChecked(self.config.get('is_monitoring', False))

        options_layout.addWidget(self.auto_start_checkbox)
        options_layout.addWidget(self.show_notifications_checkbox)
        options_layout.addWidget(self.monitoring_checkbox)
        options_layout.addStretch()
        options_group.setLayout(options_layout)

        layout.addWidget(options_group)
        layout.addStretch()

        self.basic_tab.setLayout(layout)

    # ==================== 规则设置 Tab ====================

    def init_rules_tab(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        self.rules_table = QTableWidget(0, 5)
        self.rules_table.setHorizontalHeaderLabels(["开关", "后缀名", "关键词", "目标目录", ""])

        header = self.rules_table.horizontalHeader()
        # 开关列窄
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.rules_table.setColumnWidth(0, 30)
        # 后缀名列窄（约60px）
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.rules_table.setColumnWidth(1, 60)
        # 关键词列拉伸
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        # 目标目录列拉伸
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        # 删除按钮列窄
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.rules_table.setColumnWidth(4, 36)

        self.rules_table.verticalHeader().setVisible(False)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rules_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        # 支持拖拽排序
        self.rules_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.rules_table.setDragDropOverwriteMode(False)
        self.rules_table.setDropIndicatorShown(True)

        self._load_rules_from_config()

        layout.addWidget(self.rules_table, 1)

        # 两个按钮：添加规则 + 保存规则
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加规则")
        add_btn.clicked.connect(self._add_rule_row)
        save_btn = QPushButton("保存规则")
        save_btn.setToolTip("将当前表格中的规则保存到配置文件")
        save_btn.clicked.connect(self._save_rules_only)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.rules_tab.setLayout(layout)

    # ==================== 规则表格操作 ====================

    def _save_rules_only(self):
        """仅保存规则到配置文件（不关闭窗口）"""
        rules = self._collect_rules_from_table()
        self.config['rules'] = rules
        if self.config_manager.save_config(self.config):
            QMessageBox.information(self, '文件自动分类器', '规则已保存。')
        else:
            QMessageBox.warning(self, '文件自动分类器', '保存规则失败！')

    def _load_rules_from_config(self):
        rules = self.config.get('rules', [])
        for rule in rules:
            self._append_rule(rule)

    def _append_rule(self, rule=None):
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)

        # 列0：开关
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        enabled = rule.get('enabled', True) if rule else True
        chk_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        self.rules_table.setItem(row, 0, chk_item)

        # 列1：后缀名
        extensions = ','.join(rule['extensions']) if (rule and rule.get('extensions')) else ''
        self.rules_table.setItem(row, 1, QTableWidgetItem(extensions))

        # 列2：关键词
        keywords = ','.join(rule['keywords']) if (rule and rule.get('keywords')) else ''
        self.rules_table.setItem(row, 2, QTableWidgetItem(keywords))

        # 列3：目标目录（右对齐 + "+" 按钮）
        target_folder = rule.get('target_folder', '') if rule else ''
        self._set_target_cell(row, target_folder)

        # 列4："-" 删除按钮
        self._set_delete_cell(row)

    def _add_rule_row(self):
        self._append_rule(None)

    def _set_target_cell(self, row, path):
        widget = QWidget()
        hbox = QHBoxLayout()
        hbox.setContentsMargins(2, 0, 2, 0)
        hbox.setSpacing(1)

        path_edit = QLineEdit()
        path_edit.setReadOnly(True)
        path_edit.setText(path)
        path_edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        path_edit.setStyleSheet("QLineEdit { border: none; background: transparent; padding-right: 2px; }")
        path_edit.setObjectName("path_edit")

        browse_btn = QPushButton("+")
        browse_btn.setFixedWidth(24)
        browse_btn.setObjectName("browse_btn")
        browse_btn.clicked.connect(self._on_browse_target)

        hbox.addWidget(path_edit, 1)
        hbox.addWidget(browse_btn, 0)
        widget.setLayout(hbox)

        self.rules_table.setCellWidget(row, 3, widget)

    def _set_delete_cell(self, row):
        widget = QWidget()
        hbox = QHBoxLayout()
        hbox.setContentsMargins(2, 0, 2, 0)
        hbox.setSpacing(0)

        del_btn = QPushButton("-")
        del_btn.setFixedWidth(24)
        del_btn.setObjectName("del_btn")
        del_btn.clicked.connect(self._on_delete_rule)

        hbox.addWidget(del_btn)
        widget.setLayout(hbox)

        self.rules_table.setCellWidget(row, 4, widget)

    def _find_row_for_widget(self, column, object_name):
        btn = self.sender()
        if not btn:
            return -1
        for r in range(self.rules_table.rowCount()):
            w = self.rules_table.cellWidget(r, column)
            if w and w.findChild(type(btn), object_name) is btn:
                return r
        return -1

    def _on_browse_target(self):
        row = self._find_row_for_widget(3, "browse_btn")
        if row < 0:
            return
        current = self._get_target_path(row)
        folder = QFileDialog.getExistingDirectory(self, '选择目标目录', current)
        if folder:
            self._set_target_path(row, folder)

    def _on_delete_rule(self):
        row = self._find_row_for_widget(4, "del_btn")
        if row >= 0:
            self.rules_table.removeRow(row)

    def _get_target_path(self, row):
        w = self.rules_table.cellWidget(row, 3)
        if w:
            edit = w.findChild(QLineEdit, "path_edit")
            if edit:
                return edit.text()
        return ''

    def _set_target_path(self, row, path):
        w = self.rules_table.cellWidget(row, 3)
        if w:
            edit = w.findChild(QLineEdit, "path_edit")
            if edit:
                edit.setText(path)

    def _collect_rules_from_table(self):
        """从表格收集规则数据"""
        rules = []
        for row in range(self.rules_table.rowCount()):
            # 列0：开关
            chk_item = self.rules_table.item(row, 0)
            enabled = chk_item.checkState() == Qt.Checked if chk_item else True

            # 列1：后缀名
            ext_item = self.rules_table.item(row, 1)
            ext_text = ext_item.text().strip() if (ext_item and ext_item.text()) else ''
            extensions = [e.strip() for e in ext_text.split(',') if e.strip()] if ext_text else []

            # 列2：关键词
            kw_item = self.rules_table.item(row, 2)
            kw_text = kw_item.text().strip() if (kw_item and kw_item.text()) else ''
            keywords = [k.strip() for k in kw_text.split(',') if k.strip()] if kw_text else []

            # 列3：目标目录
            target_folder = self._get_target_path(row)

            rules.append({
                'enabled': enabled,
                'extensions': extensions,
                'keywords': keywords,
                'target_folder': target_folder
            })
        return rules

    # ==================== 浏览文件夹 ====================

    def browse_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择监听文件夹', self.source_folder_edit.text())
        if folder:
            self.source_folder_edit.setText(folder)

    def browse_source_folder_2(self):
        folder = QFileDialog.getExistingDirectory(self, '选择监听文件夹', self.source_folder2_edit.text())
        if folder:
            self.source_folder2_edit.setText(folder)

    # ==================== 确定/取消 ====================

    def accept(self):
        source_folder = self.source_folder_edit.text()
        source_folder_2 = self.source_folder2_edit.text()

        if not source_folder and not source_folder_2:
            QMessageBox.warning(self, '文件自动分类器 - 警告', '请至少设置一个监听文件夹！')
            self.tab_widget.setCurrentIndex(0)
            return

        # 收集规则
        rules = self._collect_rules_from_table()
        auto_start = self.auto_start_checkbox.isChecked()

        self.config['source_folder'] = source_folder
        self.config['source_folder_2'] = source_folder_2
        self.config['auto_start'] = auto_start
        self.config['show_notifications'] = self.show_notifications_checkbox.isChecked()
        self.config['is_monitoring'] = self.monitoring_checkbox.isChecked()
        self.config['rules'] = rules

        update_result = update_startup_status(auto_start)
        if not update_result:
            QMessageBox.warning(self, '文件自动分类器 - 警告', '更新开机启动设置失败，可能需要管理员权限。')
            self.config['auto_start'] = is_in_startup()

        if self.config_manager.save_config(self.config):
            # 同步监听状态到 MonitoringManager
            self.monitoring_manager.sync_monitoring_state_from_config()
            super().accept()
        else:
            QMessageBox.critical(self, '文件自动分类器 - 错误', '保存配置失败！')
