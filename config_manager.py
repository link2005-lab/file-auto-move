import os
import sys
import json
import platform
from logger import logger

DEFAULT_CONFIG = {
    "source_folder": "",
    "source_folder_2": "",
    "default_target_folder": "",
    "rules": [
        {
            "enabled": True,
            "extensions": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".jfif"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".ipa", ".apk", ".dmg", ".pkg", ".deb", ".rpm", ".exe", ".msi"],
            "keywords": [],
            "target_folder": ""
        },
        {
            "enabled": True,
            "extensions": [".py", ".json", ".js", ".html", ".css", ".java", ".c", ".cpp", ".h", ".php", ".sh", ".bat", ".xml", ".jsx", ".ts", ".tsx", ".scss", ".less", ".kt", ".cs", ".rb", ".go", ".swift", ".m", ".mm", ".bash", ".zsh", ".cmd", ".ps1", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".sql", ".lua", ".pl", ".r", ".dart", ".rs", ".vue", ".svelte", ".gradle", ".properties", ".toml", ".lock", ".gitignore", ".dockerfile", ".makefile", ".htm", ".keystore", ".json5", ".plist", ".sketch"],
            "keywords": [],
            "target_folder": ""
        }
    ],
    "is_monitoring": True,
    "auto_start": True,
    "show_notifications": True
}

def _migrate_rule(rule):
    """将旧格式规则迁移到新格式（兼容旧 category 字段）"""
    migrated = rule.copy()
    if 'enabled' not in migrated:
        migrated['enabled'] = True
    if 'keywords' not in migrated:
        migrated['keywords'] = []
    # 移除旧版 category 字段
    migrated.pop('category', None)
    return migrated


class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.config_file = self._get_config_path(config_file)
        self.config = self.load_config()
        logger.info("配置管理器初始化完成")
    
    def _get_config_path(self, config_file):
        """获取配置文件路径
        - 打包成 exe 时：保存在 exe 同目录下
        - 开发运行时：保存在源码目录下
        """
        # 判断是否被 PyInstaller 打包
        if getattr(sys, 'frozen', False):
            # 打包后：sys.executable 是 exe 路径
            base_dir = os.path.dirname(sys.executable)
        else:
            # 开发时：保存在源码目录下
            base_dir = os.path.dirname(os.path.abspath(__file__))

        config_dir = os.path.join(base_dir, 'config')
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"创建配置目录失败: {str(e)}")
            config_dir = base_dir

        return os.path.join(config_dir, config_file)
    
    def load_config(self):
        """加载配置，如果文件不存在则创建默认配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 确保顶层字段存在
                    for key, value in DEFAULT_CONFIG.items():
                        if key not in config:
                            config[key] = value
                    # 迁移旧规则格式
                    if 'rules' in config:
                        config['rules'] = [_migrate_rule(r) for r in config['rules']]
                    return config
            except Exception as e:
                logger.error(f"加载配置文件失败: {str(e)}")
        
        self.save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    def save_config(self, config):
        """保存配置"""
        try:
            config_file = self.config_file
            logger.info(f"保存配置到: {config_file}")
            # 确保目录存在
            dir_name = os.path.dirname(config_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self.config = config
            logger.info("配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            return False
            
    def get_config(self):
        return self.config
