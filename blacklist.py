import json
import os

from astrbot.api import logger


class BlacklistManager:
    def __init__(self, data_dir: str):
        self.file_path = os.path.join(data_dir, "blacklist.json")
        self.groups: list[int] = []

    def load(self):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.groups = data.get("groups", [])
        except Exception as e:
            logger.error(f"加载黑名单失败：{e}")
            self.groups = []

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"groups": self.groups}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存黑名单失败：{e}")

    def is_blacklisted(self, group_id: int) -> bool:
        return group_id in self.groups

    def add(self, group_id: int) -> bool:
        if group_id in self.groups:
            return False
        self.groups.append(group_id)
        self.save()
        return True

    def remove(self, group_id: int) -> bool:
        if group_id not in self.groups:
            return False
        self.groups.remove(group_id)
        self.save()
        return True

    def list(self) -> list[int]:
        return self.groups.copy()
