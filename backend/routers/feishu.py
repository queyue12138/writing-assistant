"""
Feishu bot router.
POST /api/feishu/event — event callback from Feishu Open Platform.
GET  /api/feishu/log   — recent event log for debugging.
GET/POST /api/feishu/config — runtime credential management.
"""
import traceback
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from backend.feishu_event import (
    parse_event, process_message, reply_message,
    set_runtime_config, get_config_status,
    get_event_log, clear_event_log,
    start_polling, stop_polling, is_polling, get_polling_status,
    poll_once,
)

router = APIRouter()


@router.post("/feishu/event")
async def feishu_event(request: Request, background_tasks: BackgroundTasks):
    """Feishu event callback. Handles URL verification and message events."""
    try:
        raw_body = await request.body()
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    # Log the raw event for debugging (truncate large bodies)
    raw_preview = raw_body.decode("utf-8", errors="replace")[:500]
    print(f"[飞书回调] RAW: {raw_preview}")

    event = parse_event(body)

    if event["type"] == "challenge":
        return JSONResponse({"challenge": event["challenge"]})

    if event["type"] == "message":
        message_id = event["message_id"]
        text = event["text"]
        background_tasks.add_task(_safe_reply, message_id, text)

    return JSONResponse({"code": 0})


async def _safe_reply(message_id: str, text: str):
    """Background task: process and reply, with full error logging."""
    try:
        print(f"[飞书Bot] 开始处理消息: {text[:80]}...")
        reply = await process_message(text)
        print(f"[飞书Bot] AI回复完成, 长度: {len(reply)}")
        result = reply_message(message_id, reply)
        print(f"[飞书Bot] 发送结果: {result}")
    except Exception:
        err = traceback.format_exc()
        print(f"[飞书Bot] 处理失败:\n{err}")
        # Try to send error message to user
        try:
            reply_message(message_id, f"抱歉，处理你的消息时出错了，请稍后重试。")
        except Exception:
            pass


@router.get("/feishu/log")
async def feishu_log():
    """Get recent event log for debugging."""
    return {"events": get_event_log(), "count": len(get_event_log())}


@router.delete("/feishu/log")
async def feishu_clear_log():
    """Clear event log."""
    clear_event_log()
    return {"ok": True}


@router.get("/feishu/config")
async def get_feishu_config():
    return get_config_status()


@router.post("/feishu/config")
async def set_feishu_config(request: Request):
    body = await request.json()
    app_id = body.get("app_id", "").strip()
    app_secret = body.get("app_secret", "").strip()

    if not app_id or not app_secret:
        return JSONResponse({"ok": False, "error": "App ID 和 App Secret 不能为空"}, status_code=400)

    set_runtime_config(app_id, app_secret)

    from backend.feishu_event import get_tenant_access_token
    try:
        token = get_tenant_access_token()
        # Auto-start polling after successful credential verification
        if not is_polling():
            start_polling(interval=8)
        return {"ok": True, "status": "已连接", "token_ok": bool(token), "polling": is_polling()}
    except Exception as e:
        return {"ok": False, "error": f"凭证验证失败：{e}", "status": "凭证无效"}


@router.get("/feishu/polling")
async def feishu_polling_status():
    """Get polling status."""
    return get_polling_status()


@router.post("/feishu/polling/start")
async def feishu_polling_start():
    """Start the polling loop (fetches messages from Feishu)."""
    if is_polling():
        return {"ok": True, "message": "轮询已在运行中"}
    ok = start_polling(interval=8)
    if ok:
        return {"ok": True, "message": "轮询已启动（每8秒检查一次新消息）"}
    else:
        return {"ok": False, "error": "请先配置 App ID 和 App Secret"}


@router.post("/feishu/polling/stop")
async def feishu_polling_stop():
    """Stop the polling loop."""
    stop_polling()
    return {"ok": True, "message": "轮询已停止"}


@router.post("/feishu/polling/once")
async def feishu_polling_once():
    """Run a single polling cycle immediately."""
    status = get_config_status()
    if not status["configured"]:
        return {"ok": False, "error": "请先配置凭证"}
    count = await poll_once()
    return {"ok": True, "processed": count}
