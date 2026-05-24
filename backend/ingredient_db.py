import json
import os
import time
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ingredients.json")
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recommendation_history.json")

SEASONS_MAP = {
    1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
    6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋", 12: "冬",
}

WEATHER_KEYWORDS = {
    "炎热": ["炎热", "闷热", "燥热", "高温", "热"],
    "闷热": ["闷热", "潮湿", "湿", "多雨", "梅雨"],
    "潮湿": ["潮湿", "多雨", "湿气", "闷", "梅雨"],
    "干燥": ["干燥", "燥热", "秋燥", "干"],
    "寒凉": ["寒", "冷", "凉", "降温", "冬", "寒凉"],
    "寒湿": ["寒湿", "阴冷", "湿冷"],
}


class IngredientDatabase:

    def __init__(self):
        self._ingredients = []
        self._history = {"history": []}
        self._load()

    def _load(self):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._ingredients = data.get("ingredients", [])

        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                self._history = json.load(f)
        else:
            self._history = {"history": []}

    def _save_history(self):
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(self._history, f, ensure_ascii=False, indent=2)

    def _get_current_season(self, season_input: str = "") -> str:
        if season_input and season_input in ("春", "夏", "秋", "冬"):
            return season_input
        month = time.localtime().tm_mon
        return SEASONS_MAP.get(month, "春")

    def _classify_weather(self, weather_text: str) -> list[str]:
        types = []
        if not weather_text:
            return []
        for weather_type, keywords in WEATHER_KEYWORDS.items():
            for kw in keywords:
                if kw in weather_text:
                    types.append(weather_type)
                    break
        return list(set(types))

    def get_recently_recommended(self, days: int = 30) -> set[str]:
        cutoff = time.time() - days * 24 * 3600
        recent = set()
        for entry in self._history.get("history", []):
            try:
                entry_time = time.mktime(time.strptime(entry["date"], "%Y-%m-%d"))
                if entry_time >= cutoff:
                    for ing in entry.get("ingredients", []):
                        recent.add(ing)
            except (ValueError, KeyError):
                pass
        return recent

    def record_recommendation(self, ingredient_ids: list[str]):
        today = time.strftime("%Y-%m-%d")
        entry = {"date": today, "ingredients": ingredient_ids}
        self._history.setdefault("history", []).append(entry)
        self._prune_history()
        self._save_history()

    def _prune_history(self, days: int = 60):
        cutoff = time.time() - days * 24 * 3600
        self._history["history"] = [
            e for e in self._history.get("history", [])
            if time.mktime(time.strptime(e["date"], "%Y-%m-%d")) >= cutoff
        ]

    def query(self, weather: str = "", season: str = "", ingredients_hint: str = "",
              extra: str = "", exclude_recent_days: int = 30) -> list[dict]:
        current_season = self._get_current_season(season)
        weather_types = self._classify_weather(weather)
        recent = self.get_recently_recommended(exclude_recent_days)
        hint_ids = set()
        if ingredients_hint:
            hint_ids = {ing["id"] for ing in self._ingredients
                        if ing["name"] in ingredients_hint}

        scored = []
        for ing in self._ingredients:
            score = 0

            # 季节匹配
            if current_season in ing.get("seasons", []):
                score += 3
            elif ing.get("seasons") and len(ing["seasons"]) == 4:
                score += 1

            # 天气匹配
            for wt in weather_types:
                if wt in ing.get("weather", []):
                    score += 3
                    break
            if weather_types and "任何" in ing.get("weather", []):
                score += 1

            # 用户偏好的食材
            if ing["id"] in hint_ids:
                score += 5

            # 关键词匹配（额外要求中含有关键词）
            if extra:
                for kw in ing.get("keywords", []):
                    if kw in extra:
                        score += 2
                        break
                for bf in ing.get("benefits", []):
                    if any(kw in extra for kw in [bf]):
                        score += 2
                        break

            # 近期推荐过的降权
            if ing["id"] in recent:
                score -= 10

            if score > 0 or ing["id"] in hint_ids:
                scored.append((score, ing))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored]

    def recommend(self, weather: str = "", season: str = "", ingredients_hint: str = "",
                  extra: str = "", top_n: int = 8) -> list[dict]:
        results = self.query(weather, season, ingredients_hint, extra)
        selected = results[:top_n]
        self.record_recommendation([ing["id"] for ing in selected])
        return selected

    def format_for_prompt(self, ingredients: list[dict], include_pairings: bool = True) -> str:
        lines = []
        for ing in ingredients:
            line = (f"- **{ing['name']}**（{ing['nature']}性，归{','.join(ing['meridians'])}经）"
                    f"\n  功效：{'、'.join(ing['benefits'])}"
                    f"\n  适合：{'、'.join(ing['keywords'])}"
                    f"\n  烹饪：{'、'.join(ing['methods'])}")
            if include_pairings:
                line += f"\n  搭配：{'、'.join(ing['pairings'])}"
            lines.append(line)
        return "\n".join(lines)

    def get_all_categories(self) -> dict:
        cats = defaultdict(list)
        for ing in self._ingredients:
            cats[ing["category"]].append(ing["name"])
        return dict(cats)

    def get_recent_history(self, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 24 * 3600
        return [e for e in self._history.get("history", [])
                if time.mktime(time.strptime(e["date"], "%Y-%m-%d")) >= cutoff]

    @property
    def total_count(self) -> int:
        return len(self._ingredients)


_db_instance = None


def get_db() -> IngredientDatabase:
    global _db_instance
    if _db_instance is None:
        _db_instance = IngredientDatabase()
    return _db_instance
