"""
Feishu bot event handler.
Handles URL verification, message receiving (v1 + v2 formats),
and replying via Feishu Open API.
"""
import json
import time
import asyncio
import urllib.request
from datetime import datetime, timezone, timedelta

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFY_TOKEN,
)
from backend.deepseek_client import chat_single
from backend.prompts import CHAT_SYSTEM_PROMPT

# In-memory token cache and runtime config overrides
_token_cache = {"token": "", "expires_at": 0}
_runtime_app_id = ""
_runtime_app_secret = ""

# Event log for debugging (last 50 events)
_event_log = []
LOG_MAX = 50

# Polling state
_polling_active = False
_processed_message_ids: set = set()
_MAX_PROCESSED_IDS = 500

# Per-chat conversation history (polling mode uses chat_id as key)
# {chat_key: {"messages": [...], "last_active": timestamp}}
_conversations: dict = {}
_CONV_MAX_MESSAGES = 20
_CONV_TTL = 3600  # 1 hour TTL for inactive conversations

# Max Feishu text message length (bytes); leave margin for JSON overhead
_MAX_REPLY_CHARS = 12000

tz_utc8 = timezone(timedelta(hours=8))


def _get_or_create_conversation(chat_key: str) -> list:
    """Return (and optionally create) a conversation message list, pruning expired ones."""
    now = time.time()
    # Purge expired conversations
    expired = [k for k, v in _conversations.items()
               if now - v.get("last_active", 0) > _CONV_TTL]
    for k in expired:
        del _conversations[k]

    if chat_key not in _conversations:
        _conversations[chat_key] = {"messages": [], "last_active": now}
    else:
        _conversations[chat_key]["last_active"] = now

    return _conversations[chat_key]["messages"]


def _split_long_reply(text: str, max_chars: int = _MAX_REPLY_CHARS) -> list[str]:
    """Split a long reply into multiple messages that fit Feishu's limits."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    total = (len(text) + max_chars - 1) // max_chars
    idx = 0

    while remaining:
        idx += 1
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Split at the last double-newline within the limit
        slice_point = max_chars
        chunk = remaining[:max_chars]
        # Try paragraph break first, then sentence break, then word break
        for sep in ("\n\n", "\n", "。", ".", "，"):
            last = chunk.rfind(sep)
            if last > max_chars // 2:
                slice_point = last + len(sep)
                break

        chunk = remaining[:slice_point].rstrip()
        chunk += f"\n\n（{idx}/{total}）"
        chunks.append(chunk)
        remaining = remaining[slice_point:].lstrip()

    return chunks


# Common ingredient/recipe names to detect in conversation for dedup
_COMMON_ITEMS = [
    "薄荷", "柠檬", "绿茶", "红茶", "乌龙", "普洱", "菊花", "玫瑰", "桂花",
    "红枣", "桂圆", "枸杞", "当归", "黄芪", "党参", "生姜", "陈皮", "山楂",
    "薏米", "红豆", "绿豆", "黑豆", "莲子", "百合", "银耳", "雪梨", "枇杷",
    "姜枣茶", "酸梅汤", "绿豆汤", "银耳羹", "花茶", "果茶", "奶茶", "奶盖",
    "鸡汤", "排骨汤", "鱼汤", "骨头汤", "小米粥", "八宝粥", "南瓜粥", "皮蛋瘦肉粥",
    "凉拌", "清炒", "红烧", "炖", "蒸", "煲", "煮", "烤", "煎", "炸",
    "蜂蜜", "冰糖", "红糖", "黑糖", "姜", "蒜", "葱", "辣椒", "花椒",
    "山药", "红薯", "南瓜", "冬瓜", "苦瓜", "黄瓜", "番茄", "菠菜", "芹菜",
    "苹果", "香蕉", "橙子", "柚子", "葡萄", "草莓", "蓝莓", "猕猴桃",
]


def _extract_mentioned_items(recent_messages: list) -> set:
    """Extract ingredient/recipe names mentioned in recent conversation."""
    found = set()
    text = " ".join(m["content"] for m in recent_messages if isinstance(m, dict))
    for item in _COMMON_ITEMS:
        if item in text:
            found.add(item)
    return found


def _log_event(entry: dict):
    """Record an event for debugging."""
    entry["_time"] = datetime.now(tz_utc8).strftime("%H:%M:%S")
    _event_log.insert(0, entry)
    if len(_event_log) > LOG_MAX:
        _event_log.pop()
    # Print to console for live debugging
    print(f"[飞书Bot] {entry.get('type','?')} | {entry.get('summary','')}")


def get_event_log() -> list:
    """Return recent event log for the debug panel."""
    return _event_log


def clear_event_log():
    _event_log.clear()


def set_runtime_config(app_id: str, app_secret: str) -> None:
    global _runtime_app_id, _runtime_app_secret
    _runtime_app_id = app_id
    _runtime_app_secret = app_secret
    _token_cache["token"] = ""
    _token_cache["expires_at"] = 0


def get_config_status() -> dict:
    app_id = _runtime_app_id or FEISHU_APP_ID
    app_secret = _runtime_app_secret or FEISHU_APP_SECRET
    return {
        "configured": bool(app_id and app_secret),
        "app_id_masked": (app_id[:8] + "..." if len(app_id) > 8 else app_id) if app_id else "",
    }


def get_tenant_access_token() -> str:
    """Get or refresh Feishu tenant_access_token."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    app_id = _runtime_app_id or FEISHU_APP_ID
    app_secret = _runtime_app_secret or FEISHU_APP_SECRET

    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID 和 FEISHU_APP_SECRET 未配置")

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({
        "app_id": app_id,
        "app_secret": app_secret,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())

    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg', data)}")

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data.get("expire", 7200)
    return _token_cache["token"]


def parse_event(body: dict) -> dict:
    """
    Parse Feishu event (v1 and v2 formats).
    Returns:
        {"type": "challenge", "challenge": "..."}
        {"type": "message", "message_id": "...", "text": "..."}
        {"type": "unknown", "body_keys": [...]}
    """
    body_keys = list(body.keys())

    # ── URL verification (both v1 and v2 use same format) ──
    challenge = body.get("challenge")
    token = body.get("token", "")
    if challenge and body.get("type") == "url_verification":
        _log_event({"type": "challenge", "summary": f"token={token[:8]}... challenge={challenge[:8]}..."})
        return {"type": "challenge", "challenge": challenge}

    # ── v2 event format: {"schema":"2.0", "header":{...}, "event":{...}} ──
    if body.get("schema") == "2.0":
        header = body.get("header", {})
        event = body.get("event", {})
        event_type = header.get("event_type", "")

        if event_type == "im.message.receive_v1":
            return _parse_v2_message(event)

        _log_event({"type": "v2_unknown", "summary": f"event_type={event_type}", "body_keys": body_keys})
        return {"type": "unknown", "body_keys": body_keys}

    # ── v1 event format: {"type":"event_callback", "event":{...}} ──
    if body.get("type") == "event_callback":
        inner = body.get("event", {})
        return _parse_v1_message(inner)

    _log_event({"type": "unknown", "summary": "unrecognized format", "body_keys": body_keys})
    return {"type": "unknown", "body_keys": body_keys}


def _parse_v2_message(event: dict) -> dict:
    """Parse v2 message event."""
    msg = event.get("message", {})
    sender = event.get("sender", {})

    if msg.get("message_type") != "text":
        _log_event({"type": "non_text", "summary": f"msg_type={msg.get('message_type')}"})
        return {"type": "unknown"}

    message_id = msg.get("message_id", "")
    raw_content = msg.get("content", "{}")

    # Parse text from content JSON
    try:
        content_obj = json.loads(raw_content)
        text = content_obj.get("text", raw_content)
    except (json.JSONDecodeError, TypeError):
        text = raw_content

    # v2 sender: {"sender_id": {"open_id": "ou_...", "union_id": "on_..."}}
    sender_id_obj = sender.get("sender_id", {})
    open_id = sender_id_obj.get("open_id", "") if isinstance(sender_id_obj, dict) else str(sender_id_obj)

    if not text or not message_id:
        return {"type": "unknown"}

    _log_event({
        "type": "message_v2",
        "summary": f"msg_id={message_id[:12]}... text={text[:50]}...",
        "open_id": open_id,
    })

    return {
        "type": "message",
        "message_id": message_id,
        "text": text,
        "open_id": open_id,
    }


def _parse_v1_message(inner: dict) -> dict:
    """Parse v1 message event."""
    msg = inner.get("message", {})
    sender = inner.get("sender", {})

    if msg.get("message_type") != "text":
        return {"type": "unknown"}

    message_id = msg.get("message_id", "")
    raw_content = msg.get("content", "{}")

    try:
        content_obj = json.loads(raw_content)
        text = content_obj.get("text", raw_content)
    except (json.JSONDecodeError, TypeError):
        text = raw_content

    if not text or not message_id:
        return {"type": "unknown"}

    open_id = sender.get("open_id", "")

    _log_event({
        "type": "message_v1",
        "summary": f"msg_id={message_id[:12]}... text={text[:50]}...",
    })

    return {
        "type": "message",
        "message_id": message_id,
        "text": text,
        "open_id": open_id,
    }


def reply_message(message_id: str, content: str) -> dict:
    """Reply to a Feishu message. Returns result dict for logging."""
    try:
        token = get_tenant_access_token()
    except RuntimeError as e:
        err = str(e)
        _log_event({"type": "reply_error", "summary": err})
        return {"ok": False, "error": err}

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"

    body = json.dumps({
        "content": json.dumps({"text": content}, ensure_ascii=False),
        "msg_type": "text",
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        code = data.get("code", -1)
        _log_event({
            "type": "reply_sent",
            "summary": f"code={code} msg_id={message_id[:12]}... reply_len={len(content)}",
        })
        return {"ok": code == 0, "code": code, "msg": data.get("msg", "")}
    except Exception as e:
        _log_event({"type": "reply_network_error", "summary": str(e)})
        return {"ok": False, "error": str(e)}


async def process_message(text: str, chat_key: str = "") -> str:
    """Process user message through AI and return reply.

    chat_key: used to maintain per-conversation history (e.g. chat_id).
    """
    now = time.time()
    # Get (or create) conversation history for this chat
    conv = _get_or_create_conversation(chat_key) if chat_key else []

    # Build system prompt that explains the bot's full capabilities
    system_prompt = CHAT_SYSTEM_PROMPT.format(
        weather="未知（飞书对话中未指定）",
        season="未知",
        ingredients="未知",
    )

    capability_prompt = (
        "你正在通过飞书与团队成员对话。请充分发挥养生美食创作助手的全部能力，"
        "根据用户的需求直接输出有价值的内容。\n\n"
        "你可以做的事情：\n"
        "1. 🌿 根据季节/天气/身体状态推荐养生食材\n"
        "2. 📖 根据食材生成详细食谱（含用量、步骤、技巧）\n"
        "3. 🍳 将食谱拆解为烹饪方法步骤\n"
        "4. 🎙️ 撰写短视频口播文案（支持30/60/90/120/180秒）\n"
        "5. 🎬 生成专业拍摄分镜脚本\n"
        "6. 🛡️ 审核口播文案（检测平台违规风险）\n"
        "7. 💬 回答养生、烹饪相关问题\n\n"
        "⚠️ 重要规则：\n"
        "- 用户说「生成口播」「写文案」「配音稿」→ 直接生成口播文案，默认60秒\n"
        "- 用户说「分镜」「拍摄脚本」→ 生成拍摄分镜表\n"
        "- 用户说「食谱」「怎么做」→ 生成详细食谱\n"
        "- 用户说「推荐食材」「吃什么」→ 推荐养生食材\n"
        "- 用户说「审核」「检查」→ 审核文案合规性\n"
        "- 回答要直接可用，少说客套话，多给实际内容\n"
        "- 口播文案要标注每段时间，确保时长精准\n"
        "- 如果用户没有指定时长，口播默认60秒\n"
        "- 对话是上下文连续的，请结合之前的对话理解用户意图\n\n"
        "🛡️ 平台安全规则（极其重要，必须遵守）：\n"
        "- 你是美食创作者，不是医生！生成的所有内容都要用美食语言，不用医疗语言\n"
        "- 禁用医疗词：气血、阴虚、阳虚、上火、祛湿、补肾、排毒、治疗、药方、中医认为\n"
        "- 禁用伪传统词：古法、古方、秘制、祖传、宫廷、皇家、千年、百年、老中医、郎中\n"
        "- 禁用营销腔：家人们、姐妹们、绝绝子、yyds、划重点、闭眼冲、亲测有效、天花板\n"
        "- 不说\"手脚冰凉\"，说\"天冷手脚容易冷\"\n"
        "- 不说\"补气血\"，说\"元气满满\"\"状态越来越好\"\n"
        "- 不说\"古法\"\"祖传\"，说\"家常做法\"\"老一辈传下来的\"\n"
        "- 不说\"秘制\"\"宫廷\"，说\"独家做法\"\"讲究的吃法\"\n"
        "- 不说任何疾病名称（高血压、糖尿病、贫血等）\n"
        "- 用\"老一辈讲究\"\"传统饮食智慧\"代替\"中医认为\"\n"
        "- 用\"汤膳\"\"传统炖品\"代替\"药膳\"\n"
        "- 结尾提醒：饮食搭配是一个长期的过程，适合自己的才是最好的\n\n"
        "✍️ 写作风格（去AI味，生活化）：\n"
        "- 像跟朋友聊天一样写，自然口语化，不要写说明书\n"
        "- 用短句，每句话不超过20字\n"
        "- 直接说重点，不说\"今天给大家分享\"\"接下来我们来\"等废话开头\n"
        "- 不用\"众所周知\"\"值得注意的是\"\"综上所述\"等书面语\n"
        "- 描述食物用具体的口感、气味、颜色，不要堆砌空洞形容词\n\n"
        "🔄 避免重复推荐（极其重要）：\n"
        "- 查看上方对话历史，如果某个食材或食谱已经在最近的对话中出现过，不要再推荐\n"
        "- 同一场对话中，不能连续推荐相同的茶饮、汤品或食谱\n"
        "- 如果用户连续问相似的问题，主动换一个不同的推荐\n"
        "- 可以说：\"上次推荐了A，这次给你换个口味，试试B\""
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": capability_prompt},
    ]

    # Scan recent conversation for already-mentioned items to avoid
    recently_mentioned = _extract_mentioned_items(conv[-6:]) if conv else set()

    # Include recent conversation history
    if conv:
        messages.extend(conv[-_CONV_MAX_MESSAGES:])

    # Explicit reminder about what to avoid
    if recently_mentioned:
        avoid_hint = (
            "\n\n⚠️ 本轮对话中已经出现过的食材/食谱："
            + "、".join(sorted(recently_mentioned))
            + "。请不要再推荐这些，换个不同的！"
        )
        messages.append({"role": "user", "content": text + avoid_hint})
    else:
        messages.append({"role": "user", "content": text})

    reply = await chat_single(messages, max_tokens=4096)

    if not reply:
        return "抱歉，AI 未生成有效回复，请稍后重试。"

    # Store in conversation history
    if chat_key:
        conv.append({"role": "user", "content": text})
        conv.append({"role": "assistant", "content": reply})
        # Trim to max
        while len(conv) > _CONV_MAX_MESSAGES * 2:
            conv.pop(0)
            conv.pop(0)

    return reply


# ═══════════════════════════════════════════════════
#  Polling mode — server actively fetches messages from Feishu
#  No public URL needed. Requires APP_ID + APP_SECRET.
# ═══════════════════════════════════════════════════

def _feishu_api_get(path: str, params: dict = None) -> dict:
    """Make a GET request to the Feishu Open API."""
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis{path}"
    if params:
        import urllib.parse
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        url += "?" + qs

    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        _log_event({"type": "api_http_error", "summary": f"{e.code} {path}: {body[:200]}"})
        raise


def fetch_recent_messages(page_size: int = 20) -> list:
    """
    Fetch recent unread messages from Feishu via polling.

    IMPORTANT: Feishu's /im/v1/chats API only returns GROUP chats the bot
    has been added to. It does NOT return DM/P2P conversations.  To use
    polling mode, add the bot to a group chat and send messages there.

    If you need DM replies, deploy to Render (public URL) and use the
    event callback endpoint /api/feishu/event instead.
    """
    messages = []
    try:
        chat_data = _feishu_api_get("/im/v1/chats", {"page_size": 30})
    except Exception as e:
        _log_event({"type": "poll_chats_error", "summary": str(e)})
        return messages

    chats = chat_data.get("data", {}).get("items", [])
    _log_event({"type": "poll_chats_ok", "summary": f"找到 {len(chats)} 个群聊会话"})

    if not chats:
        _log_event({
            "type": "poll_no_chats",
            "summary": "未找到任何群聊。请将机器人添加到飞书群聊中，然后发送消息。注意：私聊/DM无法通过轮询获取，只有群聊消息能被轮询到。",
        })

    for chat in chats[:10]:  # Check up to 10 most recent chats
        chat_id = chat.get("chat_id", "")
        try:
            msg_data = _feishu_api_get(f"/im/v1/messages", {
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": page_size,
                "sort_type": "ByCreateTimeDesc",
            })
        except Exception as e:
            _log_event({"type": "poll_msg_error", "summary": f"chat={chat_id[:8]}... {e}"})
            continue

        items = msg_data.get("data", {}).get("items", [])
        _log_event({"type": "poll_msg_list", "summary": f"chat={chat_id[:12]}... 共{len(items)}条消息"})

        for item in items:
            msg_id = item.get("message_id", "")
            msg_type = item.get("msg_type", "")
            sender_type = item.get("sender", {}).get("sender_type", "?")

            if msg_id in _processed_message_ids:
                continue
            if sender_type != "user":
                continue
            if msg_type != "text":
                continue

            # Only process messages from the last 60 seconds to avoid
            # re-processing old messages after a restart
            create_time_ms = int(item.get("create_time", "0"))
            if create_time_ms:
                msg_age = time.time() - create_time_ms / 1000
                if msg_age > 60:
                    _log_event({"type": "poll_msg_skip", "summary": f"msg_id={msg_id[:16]} too old ({msg_age:.0f}s)"})
                    continue

            raw_content = item.get("body", {}).get("content", "{}")
            try:
                content_obj = json.loads(raw_content)
                text = content_obj.get("text", raw_content)
            except (json.JSONDecodeError, TypeError):
                text = raw_content

            if text and msg_id:
                messages.append({
                    "message_id": msg_id,
                    "text": text,
                    "chat_id": chat_id,
                })
                _processed_message_ids.add(msg_id)

    # Trim processed set
    while len(_processed_message_ids) > _MAX_PROCESSED_IDS:
        _processed_message_ids.pop()

    return messages


def fetch_p2p_messages(page_size: int = 5) -> list:
    """
    Fetch recent messages from P2P (DM) conversations.

    Feishu does not provide a direct "list p2p chats" endpoint in all API versions,
    so we use a best-effort approach to discover P2P conversations the bot has received
    messages from and poll them for new messages.
    """
    messages = []
    p2p_chat_ids = _discover_p2p_chats()
    if not p2p_chat_ids:
        return messages

    for chat_id in p2p_chat_ids:
        try:
            msg_data = _feishu_api_get(f"/im/v1/messages", {
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": page_size,
                "sort_type": "ByCreateTimeDesc",
            })
        except Exception:
            continue

        items = msg_data.get("data", {}).get("items", [])
        for item in items:
            msg_id = item.get("message_id", "")
            msg_type = item.get("msg_type", "")

            if msg_id in _processed_message_ids:
                continue
            if item.get("sender", {}).get("sender_type") != "user":
                continue
            if msg_type != "text":
                continue

            create_time_ms = int(item.get("create_time", "0"))
            if create_time_ms:
                msg_age = time.time() - create_time_ms / 1000
                if msg_age > 60:
                    continue

            raw_content = item.get("body", {}).get("content", "{}")
            try:
                content_obj = json.loads(raw_content)
                text = content_obj.get("text", raw_content)
            except (json.JSONDecodeError, TypeError):
                text = raw_content

            if text and msg_id:
                messages.append({
                    "message_id": msg_id,
                    "text": text,
                    "chat_id": chat_id,
                })
                _processed_message_ids.add(msg_id)

    return messages


# Known P2P chat IDs discovered from replies
_known_p2p_chats: set = set()


def _discover_p2p_chats() -> set:
    """Discover P2P chat IDs using available Feishu API endpoints."""
    discovered = set(_known_p2p_chats)

    # Attempt 1: Try the p2p_chats list endpoint (available in some API versions)
    try:
        data = _feishu_api_get("/im/v1/p2p_chats", {"page_size": 20})
        items = data.get("data", {}).get("items", [])
        for item in items:
            chat_id = item.get("chat_id", "")
            if chat_id:
                discovered.add(chat_id)
        _log_event({"type": "p2p_discover", "summary": f"通过p2p_chats接口发现 {len(items)} 个P2P对话"})
    except Exception:
        pass

    # Attempt 2: Try the conversations list endpoint
    try:
        data = _feishu_api_get("/im/v1/conversations", {"page_size": 20})
        items = data.get("data", {}).get("items", [])
        for item in items:
            chat_id = item.get("id", "") or item.get("chat_id", "")
            if chat_id:
                discovered.add(chat_id)
        _log_event({"type": "p2p_discover", "summary": f"通过conversations接口发现 {len(items)} 个对话"})
    except Exception:
        pass

    return discovered


def register_p2p_chat(chat_id: str):
    """Register a P2P chat ID so it will be polled in the future."""
    _known_p2p_chats.add(chat_id)


async def poll_once() -> int:
    """Run one polling cycle. Returns number of messages processed."""
    app_id = _runtime_app_id or FEISHU_APP_ID
    if not app_id:
        return 0

    # Fetch from both group chats and P2P chats
    group_messages = []
    p2p_messages = []
    try:
        group_messages = fetch_recent_messages(page_size=5)
    except Exception as e:
        _log_event({"type": "poll_error", "summary": str(e)})

    try:
        p2p_messages = fetch_p2p_messages(page_size=5)
    except Exception as e:
        _log_event({"type": "poll_p2p_error", "summary": str(e)})

    all_messages = group_messages + p2p_messages
    count = 0
    for msg in all_messages:
        try:
            chat_key = msg.get("chat_id", "")
            reply = await process_message(msg["text"], chat_key)
            # Split long replies into multiple messages
            chunks = _split_long_reply(reply)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)  # Small delay between chunks
                result = reply_message(msg["message_id"], chunk)
                if result.get("ok"):
                    count += 1
        except Exception as e:
            _log_event({"type": "poll_reply_error", "summary": str(e)})

    if all_messages:
        _log_event({"type": "poll_cycle", "summary": f"processed {count}/{len(all_messages)} messages (group={len(group_messages)} p2p={len(p2p_messages)})"})
    return count


async def _polling_loop(interval: int = 8):
    """Background polling loop. Checks for new messages every `interval` seconds."""
    global _polling_active
    _polling_active = True
    _log_event({"type": "poll_start", "summary": f"interval={interval}s"})

    while _polling_active:
        try:
            await poll_once()
        except Exception as e:
            _log_event({"type": "poll_loop_error", "summary": str(e)})
        await asyncio.sleep(interval)


def start_polling(interval: int = 8):
    """Start the background polling loop."""
    global _polling_active
    if _polling_active:
        return False
    app_id = _runtime_app_id or FEISHU_APP_ID
    if not app_id:
        return False
    asyncio.ensure_future(_polling_loop(interval))
    return True


def stop_polling():
    """Stop the background polling loop."""
    global _polling_active
    _polling_active = False
    _log_event({"type": "poll_stop", "summary": "stopped"})


def is_polling() -> bool:
    return _polling_active


def get_polling_status() -> dict:
    return {
        "active": _polling_active,
        "processed_count": len(_processed_message_ids),
    }
