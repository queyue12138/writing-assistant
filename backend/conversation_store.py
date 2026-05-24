import json
import os
import uuid
import time
from config import CONVERSATIONS_DIR


class ConversationStore:

    def __init__(self):
        os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
        self._cache = {}

    def _file_path(self, conv_id: str) -> str:
        return os.path.join(CONVERSATIONS_DIR, f"{conv_id}.json")

    def create(self, title: str = "新对话") -> dict:
        conv = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [],
        }
        self._save(conv)
        return conv

    def get(self, conv_id: str) -> dict | None:
        if conv_id in self._cache:
            return self._cache[conv_id]
        path = self._file_path(conv_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            conv = json.load(f)
        self._cache[conv_id] = conv
        return conv

    def update(self, conv_id: str, messages: list, title: str = None):
        conv = self.get(conv_id)
        if conv is None:
            conv = self.create(title or "新对话")
            conv_id = conv["id"]
        conv["messages"] = messages
        conv["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if title:
            conv["title"] = title
        elif messages and not conv.get("title") or conv.get("title") == "新对话":
            first_user = next((m["content"] for m in messages if m["role"] == "user"), None)
            if first_user:
                conv["title"] = first_user[:30]
        self._save(conv)
        return conv

    def delete(self, conv_id: str):
        path = self._file_path(conv_id)
        if os.path.exists(path):
            os.remove(path)
        self._cache.pop(conv_id, None)

    def list_all(self) -> list:
        result = []
        for fname in sorted(os.listdir(CONVERSATIONS_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            conv_id = fname.replace(".json", "")
            try:
                conv = self.get(conv_id)
                if conv:
                    result.append({
                        "id": conv["id"],
                        "title": conv["title"],
                        "created_at": conv["created_at"],
                        "updated_at": conv["updated_at"],
                        "message_count": len(conv["messages"]),
                    })
            except (json.JSONDecodeError, KeyError):
                pass
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)

    def _save(self, conv: dict):
        path = self._file_path(conv["id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
        self._cache[conv["id"]] = conv
