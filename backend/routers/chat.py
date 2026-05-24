import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from backend.deepseek_client import chat_stream
from backend.ingredient_db import get_db
from backend.prompts import CHAT_SYSTEM_PROMPT, CHAT_CONTEXT_TEMPLATE, CATEGORY_PROMPTS
from backend.conversation_store import ConversationStore

router = APIRouter()
store = ConversationStore()


def build_context_message(body: dict) -> str:
    base = CHAT_CONTEXT_TEMPLATE.format(
        weather=body.get("weather", ""),
        season=body.get("season", ""),
        ingredients=body.get("ingredients", ""),
        recipe=body.get("recipe", ""),
        cooking_method=body.get("cooking_method", ""),
    )
    db = get_db()
    if body.get("weather") or body.get("ingredients"):
        candidates = db.query(body.get("weather", ""), body.get("season", ""),
                             body.get("ingredients", ""), exclude_recent_days=30)
        if candidates:
            recent = db.get_recent_history(30)
            recent_names = set()
            for e in recent:
                for ing_id in e.get("ingredients", []):
                    for ing in candidates:
                        if ing["id"] == ing_id:
                            recent_names.add(ing["name"])
            top = candidates[:10]
            db_ctx = "\n\n📦 本地食材数据库匹配（共{}种，辅助参考，*为近期推荐过请回避。用户对话指令优先）：\n".format(len(candidates))
            db_ctx += "\n".join(
                f"- {'⚠️ ' if ing['name'] in recent_names else '✅ '}{ing['name']}（{ing['nature']}性）{'、'.join(ing['benefits'][:2])}"
                for ing in top
            )
            return base + db_ctx
    return base


@router.post("/chat/stream")
async def stream_chat(request: Request):
    body = await request.json()
    messages_history = body.get("messages", [])
    conv_id = body.get("conversation_id", "")

    context_msg = build_context_message(body)
    category = body.get("category", "")
    if category and category in CATEGORY_PROMPTS:
        base_system = CATEGORY_PROMPTS[category]
    else:
        base_system = CHAT_SYSTEM_PROMPT

    system_msg = base_system.format(
        weather=body.get("weather", ""),
        season=body.get("season", ""),
        ingredients=body.get("ingredients", ""),
    )

    full_messages = [
        {"role": "system", "content": system_msg},
        {"role": "system", "content": context_msg},
    ]
    full_messages.extend(messages_history)

    async def generate():
        full_content = ""
        try:
            async for chunk in chat_stream(full_messages):
                full_content += chunk
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = f"\n\n> ⚠️ 出错了：{str(e)}"
            full_content += err_msg
            yield f"data: {json.dumps({'content': err_msg, 'error': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

        # 自动保存对话
        if conv_id and messages_history:
            try:
                new_messages = messages_history + [{"role": "assistant", "content": full_content}]
                store.update(conv_id, new_messages)
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/conversations")
async def list_conversations():
    return {"conversations": store.list_all()}


@router.post("/conversations")
async def create_conversation(request: Request):
    body = await request.json()
    conv = store.create(body.get("title", "新对话"))
    return {"conversation": conv}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    conv = store.get(conv_id)
    if conv is None:
        return {"error": "not found"}
    return {"conversation": conv}


@router.put("/conversations/{conv_id}")
async def save_conversation(conv_id: str, request: Request):
    body = await request.json()
    conv = store.update(conv_id, body.get("messages", []), body.get("title"))
    return {"conversation": conv}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    store.delete(conv_id)
    return {"ok": True}
