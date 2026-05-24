from fastapi import APIRouter, Request
from backend.deepseek_client import chat_single
from backend.ingredient_db import get_db
from backend.prompts import (
    INGREDIENTS_RECOMMEND_PROMPT,
    RECIPE_GENERATE_PROMPT,
    COOKING_METHOD_PROMPT,
    SCRIPT_GENERATE_PROMPT,
    STORYBOARD_PROMPT,
    CONTENT_AUDIT_PROMPT,
    CATEGORY_PROMPTS,
)

router = APIRouter()


def _make_messages(system_prompt: str, user_content: str) -> list:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _format_user_input(body: dict, user_message: str = "") -> str:
    parts = []
    if user_message:
        parts.append(f"【用户指令 · 最高优先级】\n{user_message}")
    for key, label in [("weather", "天气"), ("season", "季节"), ("ingredients", "食材"), ("extra", "额外要求")]:
        val = body.get(key, "")
        if val:
            parts.append(f"{label}：{val}")
    result = "\n".join(parts)
    if user_message:
        result += "\n\n⚠️ 以上【用户指令】是最高优先级，与辅助上下文（天气/季节/食材等）有冲突时必须优先执行用户指令。"
    return result


@router.post("/generate/ingredients")
async def recommend_ingredients(request: Request):
    body = await request.json()
    weather = body.get("weather", "")
    season = body.get("season", "")
    ingredients_hint = body.get("ingredients", "")
    extra = body.get("extra", "")
    user_message = body.get("user_message", "")

    db = get_db()
    candidates = db.query(weather, season, ingredients_hint, extra, exclude_recent_days=30)
    recent_history = db.get_recent_history(30)
    recent_names = set()
    for entry in recent_history:
        for ing_id in entry.get("ingredients", []):
            for ing in candidates:
                if ing["id"] == ing_id:
                    recent_names.add(ing["name"])

    top_matches = candidates[:15] if candidates else []
    db_context = ""
    if top_matches:
        db_context = "\n\n【本地食材数据库推荐（按匹配度排序）】\n"
        db_context += db.format_for_prompt(top_matches, include_pairings=True)
        db_context += f"\n\n本月已推荐过请避免重复的食材：{'、'.join(recent_names) if recent_names else '无'}"
        db_context += "\n请优先从上表中选取食材进行推荐，但也可以补充数据库中没有的时令食材。"

    user_input = _format_user_input(body, user_message)
    prompt = INGREDIENTS_RECOMMEND_PROMPT.format(
        weather=weather,
        season=season,
        ingredients=ingredients_hint,
        user_message=user_message or "（无特别指令，按辅助上下文推荐）",
    )
    full_prompt = prompt + db_context

    result = await chat_single(_make_messages(full_prompt, user_input))

    # 记录本次推荐
    recommended_ids = []
    for ing in top_matches:
        if ing["name"] in result:
            recommended_ids.append(ing["id"])
    if recommended_ids:
        db.record_recommendation(recommended_ids)

    return {"content": result, "db_matches": len(top_matches)}


@router.post("/generate/recipe")
async def generate_recipe(request: Request):
    body = await request.json()
    user_message = body.get("user_message", "")
    user_input = _format_user_input(body, user_message)
    prompt = RECIPE_GENERATE_PROMPT.format(
        ingredients=body.get("ingredients", ""),
        extra=body.get("extra", ""),
        user_message=user_message or "（无特别指令，按辅助上下文生成）",
    )
    result = await chat_single(_make_messages(prompt, user_input))
    return {"content": result}


@router.post("/generate/cooking")
async def generate_cooking(request: Request):
    body = await request.json()
    user_message = body.get("user_message", "")
    user_input = _format_user_input(body, user_message)
    prompt = COOKING_METHOD_PROMPT.format(
        recipe=body.get("recipe", ""),
        extra=body.get("extra", ""),
        user_message=user_message or "（无特别指令，按辅助上下文生成）",
    )
    result = await chat_single(_make_messages(prompt, user_input))
    return {"content": result}


@router.post("/generate/script")
async def generate_script(request: Request):
    body = await request.json()
    user_message = body.get("user_message", "")
    user_input = _format_user_input(body, user_message)
    duration = int(body.get("duration", 60))
    word_count = duration * 5
    prompt = SCRIPT_GENERATE_PROMPT.format(
        content=body.get("content", ""),
        extra=body.get("extra", ""),
        duration=duration,
        word_count=word_count,
        user_message=user_message or "（无特别指令，按辅助上下文生成）",
    )
    result = await chat_single(_make_messages(prompt, user_input))
    return {"content": result}


@router.post("/generate/storyboard")
async def generate_storyboard(request: Request):
    body = await request.json()
    user_message = body.get("user_message", "")
    user_input = _format_user_input(body, user_message)
    script_duration = int(body.get("script_duration", 60))
    prompt = STORYBOARD_PROMPT.format(
        content=body.get("content", ""),
        extra=body.get("extra", ""),
        script_duration=script_duration,
        user_message=user_message or "（无特别指令，按辅助上下文生成）",
    )
    result = await chat_single(_make_messages(prompt, user_input))
    return {"content": result}


@router.post("/generate/pipeline")
async def pipeline_generate(request: Request):
    """一键生成：食材 → 食谱 → 烹饪方法 → 口播文案 → 审核 → 拍摄分镜"""
    body = await request.json()
    ingredients = body.get("ingredients", "")
    extra = body.get("extra", "")
    weather = body.get("weather", "")
    season = body.get("season", "")
    provided_recipe = body.get("recipe", "")
    duration = int(body.get("duration", 60))
    word_count = duration * 5
    user_message = body.get("user_message", "")

    if not ingredients and not provided_recipe:
        return {"ok": False, "error": "请提供食材或已有食谱"}

    user_input = _format_user_input(body, user_message)
    results = {}
    default_um = user_message or "（无特别指令，按辅助上下文生成）"

    # 步骤1: 食谱（优先使用用户提供的）
    if provided_recipe.strip():
        recipe = provided_recipe.strip()
    else:
        prompt = RECIPE_GENERATE_PROMPT.format(ingredients=ingredients, extra=extra, user_message=default_um)
        recipe = await chat_single(_make_messages(prompt, user_input))
    results["recipe"] = recipe

    # 步骤2: 生成烹饪方法
    prompt = COOKING_METHOD_PROMPT.format(recipe=recipe, extra=extra, user_message=default_um)
    cooking = await chat_single(_make_messages(prompt, user_input + f"\n\n食谱内容：\n{recipe}"))
    results["cooking"] = cooking

    # 步骤3: 生成口播文案（带时长约束）
    combined = f"食谱：\n{recipe}\n\n烹饪方法：\n{cooking}"
    prompt = SCRIPT_GENERATE_PROMPT.format(
        content=combined, extra=extra, duration=duration, word_count=word_count, user_message=default_um
    )
    script = await chat_single(_make_messages(prompt, user_input + f"\n\n{combined}"))
    results["script"] = script

    # 步骤4: 内容审核（抖音/视频号标准）
    audit_prompt = CONTENT_AUDIT_PROMPT.format(script_content=script)
    audit_result = await chat_single(_make_messages(audit_prompt, ""))
    results["audit"] = audit_result

    # 步骤5: 生成拍摄分镜（基于审核后文案 + 时长）
    combined2 = f"烹饪方法：\n{cooking}\n\n配音稿（含审核建议）：\n{script}\n\n审核报告：\n{audit_result}"
    prompt = STORYBOARD_PROMPT.format(
        content=combined2, extra=extra, script_duration=duration, user_message=default_um
    )
    storyboard = await chat_single(_make_messages(prompt, user_input + f"\n\n{combined2}"))
    results["storyboard"] = storyboard

    # 记录到数据库
    db = get_db()
    recommended_ids = []
    for ing in db._ingredients:
        if ing["name"] in recipe:
            recommended_ids.append(ing["id"])
    if recommended_ids:
        db.record_recommendation(recommended_ids)

    return {"ok": True, **results}


@router.post("/generate/audit")
async def audit_script(request: Request):
    """对已有口播文案进行内容审核"""
    body = await request.json()
    script_content = body.get("content", "")
    if not script_content:
        return {"ok": False, "error": "请提供待审核的口播文案"}
    prompt = CONTENT_AUDIT_PROMPT.format(script_content=script_content)
    result = await chat_single(_make_messages(prompt, ""))
    return {"ok": True, "content": result}


@router.get("/categories")
async def list_categories():
    return {
        "categories": [
            {"id": "health_light", "name": "健康简餐", "icon": "🥗", "desc": "低脂营养轻食"},
            {"id": "gourmet", "name": "美食料理", "icon": "🍽️", "desc": "精致菜肴做法"},
            {"id": "health_tea", "name": "养生茶饮", "icon": "🍵", "desc": "节气养生茶方"},
            {"id": "seasonal", "name": "时令养生", "icon": "🌿", "desc": "顺时饮食调理"},
            {"id": "tonic", "name": "滋补炖品", "icon": "🍲", "desc": "药膳老火汤"},
            {"id": "fermented", "name": "发酵美食", "icon": "🫙", "desc": "泡菜酵素面包"},
        ]
    }


@router.get("/db/stats")
async def db_stats():
    db = get_db()
    categories = db.get_all_categories()
    recent = db.get_recent_history(30)
    recent_ids = set()
    for e in recent:
        recent_ids.update(e.get("ingredients", []))
    return {
        "total": db.total_count,
        "categories": {k: len(v) for k, v in categories.items()},
        "recently_recommended_count": len(recent_ids),
        "history_days": len(recent),
    }


@router.get("/db/history")
async def db_history():
    db = get_db()
    return {"history": db.get_recent_history(30)}


@router.post("/db/clear-history")
async def db_clear_history():
    db = get_db()
    db._history = {"history": []}
    db._save_history()
    return {"ok": True}
