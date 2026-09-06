# utils/autorole_manager.py
import copy
import json
import os
from typing import Optional, Dict, List, Any


class AutoroleManager:
    _instances = {}

    def __new__(cls, file_path: str = "data/autorole_config.json"):
        key = os.path.abspath(file_path)
        instance = cls._instances.get(key)
        if instance is None:
            instance = super().__new__(cls)
            cls._instances[key] = instance
            instance._initialized = False
        return instance

    def __init__(self, file_path: str = "data/autorole_config.json"):
        if self._initialized:
            return
        self._initialized = True
        self.file_path = file_path
        self._ensure_data_directory()
        self.config = self._load_config()

    def _ensure_data_directory(self):
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)

    def _default_config(self) -> Dict[str, Any]:
        return {
            "guilds": {},
            "default_config": {
                "enabled": False,
                "roles": {},
                "auto_assign": [],
                "dm_config": {
                    "enabled": False,
                    "title": "🌙 Bem-vindo ao Moon Tensura!",
                    "description": "Olá {user}! Seja bem-vindo ao servidor **Moon Tensura**!\n\n{roles_info}\n\nAproveite sua estadia! 🎉",
                    "footer": "Moon Tensura • Korczak Technologies",
                    "thumbnail_url": None
                }
            }
        }

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError("Configuração inválida")
            config.setdefault("guilds", {})
            config.setdefault("default_config", self._default_config()["default_config"])
            return config
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            default_config = self._default_config()
            self._save_config(default_config)
            return default_config

    def _save_config(self, config: Optional[Dict] = None):
        if config is None:
            config = self.config
        temp_path = f"{self.file_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        guild_id_str = str(guild_id)
        if guild_id_str not in self.config["guilds"]:
            self.config["guilds"][guild_id_str] = copy.deepcopy(self.config["default_config"])
            self._save_config()
        return copy.deepcopy(self.config["guilds"][guild_id_str])

    def set_guild_config(self, guild_id: int, config: Dict[str, Any]):
        self.config["guilds"][str(guild_id)] = copy.deepcopy(config)
        self._save_config()

    def is_enabled(self, guild_id: int) -> bool:
        return self.get_guild_config(guild_id).get("enabled", False)

    def get_roles(self, guild_id: int) -> Dict[str, int]:
        return copy.deepcopy(self.get_guild_config(guild_id).get("roles", {}))

    def get_auto_assign_roles(self, guild_id: int) -> List[int]:
        config = self.get_guild_config(guild_id)
        return [
            int(role_id)
            for role_name in config.get("auto_assign", [])
            if (role_id := config.get("roles", {}).get(role_name))
        ]

    def get_dm_config(self, guild_id: int) -> Dict[str, Any]:
        return copy.deepcopy(self.get_guild_config(guild_id).get("dm_config", {}))

    def is_dm_enabled(self, guild_id: int) -> bool:
        return self.get_dm_config(guild_id).get("enabled", False)

    def add_role_config(self, guild_id: int, role_name: str, role_id: int):
        config = self.get_guild_config(guild_id)
        config.setdefault("roles", {})[role_name] = str(role_id)
        self.set_guild_config(guild_id, config)

    def remove_role_config(self, guild_id: int, role_name: str):
        config = self.get_guild_config(guild_id)
        if role_name in config.get("roles", {}):
            del config["roles"][role_name]
            if role_name in config.get("auto_assign", []):
                config["auto_assign"].remove(role_name)
            self.set_guild_config(guild_id, config)

    def toggle_auto_assign(self, guild_id: int, role_name: str) -> bool:
        config = self.get_guild_config(guild_id)
        if role_name not in config.get("roles", {}):
            return False
        auto_assign = config.setdefault("auto_assign", [])
        if role_name in auto_assign:
            auto_assign.remove(role_name)
            enabled = False
        else:
            auto_assign.append(role_name)
            enabled = True
        self.set_guild_config(guild_id, config)
        return enabled

    def toggle_enabled(self, guild_id: int) -> bool:
        config = self.get_guild_config(guild_id)
        config["enabled"] = not config.get("enabled", False)
        self.set_guild_config(guild_id, config)
        return config["enabled"]

    def toggle_dm(self, guild_id: int) -> bool:
        config = self.get_guild_config(guild_id)
        dm_config = config.setdefault("dm_config", {})
        dm_config["enabled"] = not dm_config.get("enabled", False)
        self.set_guild_config(guild_id, config)
        return dm_config["enabled"]
