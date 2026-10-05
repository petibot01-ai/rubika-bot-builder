# ============================================================
# PETI RUBIKA BOT BUILDER
# Single File - FastAPI + Embedded HTML/CSS/JS
# ============================================================

import os
import time
import threading
from typing import Optional, Any

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "پتی ربات‌ساز"
API_BASE = "https://botapi.rubika.ir/v3"

app = FastAPI(title=APP_NAME)


# ============================================================
# MEMORY
# ============================================================

BOT_DATA = {
    "token": "",
    "connected": False,
    "bot": {},
    "chats": {},
    "commands": {},
    "offset": None,
    "welcome": "سلام 👋 به ربات پتی خوش آمدید.",
}

LOCK = threading.Lock()


# ============================================================
# RUBIKA API
# ============================================================

def rubika_request(
    token: str,
    method: str,
    data: Optional[dict] = None
):
    if not token:
        return {
            "ok": False,
            "error": "توکن وارد نشده است."
        }

    url = f"{API_BASE}/{token}/{method}"

    try:
        response = requests.post(
            url,
            json=data or {},
            timeout=25
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "raw": response.text
            }

        if response.ok:
            return {
                "ok": True,
                "status_code": response.status_code,
                "data": result
            }

        return {
            "ok": False,
            "status_code": response.status_code,
            "data": result
        }

    except requests.RequestException as e:
        return {
            "ok": False,
            "error": str(e)
        }


def get_me(token: str):
    return rubika_request(token, "getMe", {})


def send_message(token: str, chat_id: str, text: str):
    return rubika_request(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text
        }
    )


def get_updates(token: str, offset_id=None, limit=20):
    data = {
        "limit": limit
    }

    if offset_id:
        data["offset_id"] = offset_id

    return rubika_request(
        token,
        "getUpdates",
        data
    )


# ============================================================
# UPDATE PARSER
# ============================================================

def find_value(obj: Any, names):
    if isinstance(obj, dict):
        for name in names:
            if name in obj and obj[name] is not None:
                return obj[name]

        for value in obj.values():
            result = find_value(value, names)
            if result is not None:
                return result

    elif isinstance(obj, list):
        for item in obj:
            result = find_value(item, names)
            if result is not None:
                return result

    return None


def extract_update(update):
    """
    تلاش می‌کند از ساختارهای مختلف Update روبیکا
    chat_id و متن پیام را پیدا کند.
    """

    if not isinstance(update, dict):
        return None, None, None

    chat_id = find_value(
        update,
        [
            "chat_id",
            "chatId",
            "object_guid",
            "objectGuid"
        ]
    )

    text = find_value(
        update,
        [
            "text",
            "message_text",
            "messageText"
        ]
    )

    update_id = find_value(
        update,
        [
            "update_id",
            "updateId",
            "message_id",
            "messageId"
        ]
    )

    if text is not None:
        text = str(text)

    if chat_id is not None:
        chat_id = str(chat_id)

    if update_id is not None:
        update_id = str(update_id)

    return chat_id, text, update_id


def extract_updates(result):
    if not isinstance(result, dict):
        return []

    data = result.get("data")

    if isinstance(data, dict):
        for key in [
            "updates",
            "results",
            "items",
            "messages"
        ]:
            if isinstance(data.get(key), list):
                return data[key]

    for key in [
        "updates",
        "results",
        "items",
        "messages"
    ]:
        if isinstance(result.get(key), list):
            return result[key]

    if isinstance(data, list):
        return data

    return []


# ============================================================
# COMMAND PROCESSOR
# ============================================================

def process_command(chat_id: str, text: str):
    if not text:
        return

    clean = text.strip()

    # ----------------------------------------
    # /start
    # ----------------------------------------

    if clean.lower() == "/start":

        welcome = BOT_DATA.get(
            "welcome",
            "سلام 👋 به ربات پتی خوش آمدید."
        )

        send_message(
            BOT_DATA["token"],
            chat_id,
            welcome
        )

        return

    # ----------------------------------------
    # /help
    # ----------------------------------------

    if clean.lower() == "/help":

        commands = BOT_DATA.get("commands", {})

        if commands:
            lines = ["📚 دستورات ربات پتی:", ""]

            for name, info in commands.items():
                title = info.get("title", "")
                lines.append(
                    f"▫️ {name} {('- ' + title) if title else ''}"
                )

            message = "\n".join(lines)

        else:
            message = (
                "📚 راهنمای ربات پتی\n\n"
                "/start\n"
                "/help"
            )

        send_message(
            BOT_DATA["token"],
            chat_id,
            message
        )

        return

    # ----------------------------------------
    # CUSTOM COMMANDS
    # ----------------------------------------

    if clean.startswith("/"):
        command = clean.split()[0].lower()

        info = BOT_DATA["commands"].get(command)

        if info:
            response = info.get(
                "response",
                "دستور دریافت شد."
            )

            send_message(
                BOT_DATA["token"],
                chat_id,
                response
            )


# ============================================================
# BOT WORKER
# ============================================================

def bot_worker():
    while True:

        try:

            with LOCK:
                token = BOT_DATA.get("token")
                connected = BOT_DATA.get("connected")
                offset = BOT_DATA.get("offset")

            if not token or not connected:
                time.sleep(2)
                continue

            result = get_updates(
                token,
                offset_id=offset,
                limit=20
            )

            if not result.get("ok"):
                time.sleep(4)
                continue

            updates = extract_updates(
                result.get("data", result)
            )

            for update in updates:

                chat_id, text, update_id = extract_update(update)

                if update_id:
                    with LOCK:
                        BOT_DATA["offset"] = update_id

                if not chat_id:
                    continue

                # ------------------------------------
                # Save chat automatically
                # ------------------------------------

                with LOCK:

                    if chat_id not in BOT_DATA["chats"]:
                        BOT_DATA["chats"][chat_id] = {
                            "chat_id": chat_id,
                            "title": f"کاربر {chat_id[-8:]}",
                            "last_message": text or "",
                            "last_seen": time.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        }

                    else:
                        BOT_DATA["chats"][chat_id][
                            "last_message"
                        ] = text or ""

                        BOT_DATA["chats"][chat_id][
                            "last_seen"
                        ] = time.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                # ------------------------------------
                # Process message
                # ------------------------------------

                if text:
                    process_command(
                        chat_id,
                        text
                    )

            time.sleep(1)

        except Exception:
            time.sleep(3)


# ============================================================
# START WORKER
# ============================================================

worker_thread = threading.Thread(
    target=bot_worker,
    daemon=True
)

worker_thread.start()


# ============================================================
# MODELS
# ============================================================

class TokenRequest(BaseModel):
    token: str


class SendRequest(BaseModel):
    token: Optional[str] = None
    chat_id: str
    text: str


class WelcomeRequest(BaseModel):
    text: str


class CommandRequest(BaseModel):
    command: str
    title: str = ""
    response: str = ""


class SelectChatRequest(BaseModel):
    chat_id: str


# ============================================================
# API ROUTES
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Peti Bot Builder"
    }


@app.get("/api/status")
def api_status():

    with LOCK:
        return {
            "connected": BOT_DATA["connected"],
            "bot": BOT_DATA["bot"],
            "chats": list(
                BOT_DATA["chats"].values()
            ),
            "commands": BOT_DATA["commands"],
            "welcome": BOT_DATA["welcome"]
        }


@app.post("/api/connect")
def connect(req: TokenRequest):

    token = req.token.strip()

    if not token:
        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    result = get_me(token)

    if not result.get("ok"):
        return {
            "ok": False,
            "message": "اتصال به روبیکا انجام نشد.",
            "details": result
        }

    data = result.get("data", {})

    bot_info = {}

    if isinstance(data, dict):
        bot_info = data.get(
            "data",
            data
        )

    with LOCK:
        BOT_DATA["token"] = token
        BOT_DATA["connected"] = True
        BOT_DATA["bot"] = bot_info
        BOT_DATA["offset"] = None

    return {
        "ok": True,
        "message": "ربات با موفقیت متصل شد.",
        "bot": bot_info
    }


@app.post("/api/send")
def api_send(req: SendRequest):

    token = req.token or BOT_DATA.get("token")

    if not token:
        return {
            "ok": False,
            "message": "ابتدا ربات را متصل کنید."
        }

    if not req.chat_id:
        return {
            "ok": False,
            "message": "ابتدا یک چت انتخاب کنید."
        }

    result = send_message(
        token,
        req.chat_id,
        req.text
    )

    return result


@app.post("/api/welcome")
def save_welcome(req: WelcomeRequest):

    with LOCK:
        BOT_DATA["welcome"] = req.text

    return {
        "ok": True
    }


@app.post("/api/command")
def add_command(req: CommandRequest):

    command = req.command.strip()

    if not command.startswith("/"):
        command = "/" + command

    with LOCK:
        BOT_DATA["commands"][command] = {
            "title": req.title,
            "response": req.response
        }

    return {
        "ok": True,
        "command": command
    }


@app.delete("/api/command/{command:path}")
def delete_command(command: str):

    if not command.startswith("/"):
        command = "/" + command

    with LOCK:
        BOT_DATA["commands"].pop(
            command,
            None
        )

    return {
        "ok": True
    }


@app.post("/api/select-chat")
def select_chat(req: SelectChatRequest):

    chat = BOT_DATA["chats"].get(
        req.chat_id
    )

    if not chat:
        return {
            "ok": False,
            "message": "چت پیدا نشد."
        }

    return {
        "ok": True,
        "chat": chat
    }


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0, maximum-scale=1.0"
/>

<title>پتی ربات‌ساز</title>

<style>

*{
    box-sizing:border-box;
    margin:0;
    padding:0;
}

:root{
    --bg:#070b13;
    --bg2:#0b111d;
    --card:#0e1725;
    --card2:#101c2d;
    --border:#1c3149;
    --blue:#00aaff;
    --cyan:#00d9ff;
    --text:#f2f7ff;
    --muted:#8293a9;
    --green:#22d49b;
    --red:#ff5577;
}

body{
    font-family:
        Tahoma,
        Arial,
        sans-serif;

    background:
        radial-gradient(
            circle at 20% 0%,
            rgba(0,170,255,.12),
            transparent 32%
        ),
        radial-gradient(
            circle at 100% 20%,
            rgba(0,220,255,.07),
            transparent 30%
        ),
        var(--bg);

    color:var(--text);
    min-height:100vh;
}

/* GRID BACKGROUND */

body:before{
    content:"";
    position:fixed;
    inset:0;
    pointer-events:none;

    background-image:
        linear-gradient(
            rgba(255,255,255,.018) 1px,
            transparent 1px
        ),
        linear-gradient(
            90deg,
            rgba(255,255,255,.018) 1px,
            transparent 1px
        );

    background-size:32px 32px;
}

/* APP */

.app{
    min-height:100vh;
    position:relative;
}

/* TOPBAR */

.topbar{
    height:68px;
    display:flex;
    align-items:center;
    justify-content:space-between;

    padding:0 20px;

    border-bottom:1px solid var(--border);

    background:
        rgba(7,11,19,.88);

    backdrop-filter:blur(14px);

    position:sticky;
    top:0;
    z-index:50;
}

.brand{
    display:flex;
    align-items:center;
    gap:12px;
}

.logo{
    width:40px;
    height:40px;
    border-radius:13px;

    display:flex;
    align-items:center;
    justify-content:center;

    font-weight:900;
    font-size:20px;

    color:#001019;

    background:
        linear-gradient(
            135deg,
            var(--cyan),
            var(--blue)
        );

    box-shadow:
        0 0 25px rgba(0,190,255,.25);
}

.brand h1{
    font-size:17px;
}

.brand small{
    display:block;
    color:var(--muted);
    font-size:10px;
    margin-top:3px;
}

.menu-btn{
    width:42px;
    height:42px;

    border:1px solid var(--border);
    background:#0b1421;
    color:white;

    border-radius:12px;

    font-size:21px;
}

/* LAYOUT */

.layout{
    display:flex;
    min-height:calc(100vh - 68px);
}

/* SIDEBAR */

.sidebar{
    width:245px;
    border-left:1px solid var(--border);

    background:
        rgba(8,14,24,.92);

    padding:22px 14px;

    position:fixed;
    top:68px;
    right:0;
    bottom:0;

    z-index:40;

    transition:.25s;
}

.sidebar.hide{
    transform:translateX(270px);
}

.profile{
    padding:17px;

    border:1px solid var(--border);
    border-radius:18px;

    background:
        linear-gradient(
            135deg,
            rgba(0,180,255,.09),
            rgba(0,0,0,.1)
        );

    margin-bottom:16px;
}

.profile-icon{
    width:44px;
    height:44px;

    border-radius:50%;

    display:flex;
    align-items:center;
    justify-content:center;

    background:#11283b;
    color:var(--cyan);

    margin-bottom:11px;
}

.profile strong{
    font-size:13px;
}

.profile span{
    display:block;
    margin-top:5px;
    color:var(--muted);
    font-size:10px;
}

.nav{
    display:flex;
    flex-direction:column;
    gap:7px;
}

.nav button{
    width:100%;

    padding:13px 14px;

    border:1px solid transparent;

    background:transparent;
    color:#aebdd0;

    border-radius:12px;

    text-align:right;

    font-family:inherit;
    cursor:pointer;

    transition:.2s;
}

.nav button:hover,
.nav button.active{
    color:white;

    border-color:#174766;

    background:
        linear-gradient(
            90deg,
            rgba(0,174,255,.14),
            rgba(0,174,255,.03)
        );
}

.nav-icon{
    margin-left:9px;
}

/* CONTENT */

.content{
    flex:1;
    margin-right:245px;
    padding:28px;
    max-width:1300px;
}

.section{
    display:none;
}

.section.active{
    display:block;
}

/* HERO */

.hero{
    padding:25px;

    border:1px solid var(--border);
    border-radius:22px;

    background:
        radial-gradient(
            circle at left,
            rgba(0,180,255,.15),
            transparent 45%
        ),
        var(--card);

    margin-bottom:20px;
}

.hero h2{
    font-size:24px;
    margin-bottom:8px;
}

.hero p{
    color:var(--muted);
    font-size:12px;
    line-height:2;
}

.status{
    display:inline-flex;
    align-items:center;
    gap:7px;

    padding:7px 11px;
    border-radius:30px;

    background:#0d211d;
    color:#39e5af;

    font-size:10px;

    margin-bottom:13px;
}

.status-dot{
    width:7px;
    height:7px;
    border-radius:50%;
    background:var(--green);
    box-shadow:0 0 10px var(--green);
}

/* CARDS */

.grid{
    display:grid;
    grid-template-columns:
        repeat(4,minmax(0,1fr));

    gap:14px;

    margin-bottom:20px;
}

.card{
    border:1px solid var(--border);

    background:
        linear-gradient(
            145deg,
            rgba(18,31,49,.95),
            rgba(10,17,28,.95)
        );

    border-radius:18px;
    padding:18px;

    box-shadow:
        0 12px 35px rgba(0,0,0,.16);
}

.stat{
    min-height:120px;
}

.stat .icon{
    width:38px;
    height:38px;

    border-radius:11px;

    background:#0c2434;
    color:var(--cyan);

    display:flex;
    align-items:center;
    justify-content:center;

    margin-bottom:12px;
}

.stat strong{
    font-size:23px;
}

.stat p{
    color:var(--muted);
    font-size:10px;
    margin-top:6px;
}

/* SECTION TITLE */

.title{
    display:flex;
    align-items:center;
    justify-content:space-between;

    margin:24px 0 13px;
}

.title h3{
    font-size:15px;
}

.title span{
    color:var(--muted);
    font-size:10px;
}

/* FORMS */

.form-card{
    max-width:850px;
}

.field{
    margin-bottom:15px;
}

.field label{
    display:block;

    font-size:11px;
    color:#a9b9cc;

    margin-bottom:7px;
}

.input,
.textarea,
select{
    width:100%;

    background:#08111d;

    color:white;

    border:1px solid #1b334b;

    border-radius:12px;

    padding:13px 14px;

    font-family:inherit;
    outline:none;
}

.input:focus,
.textarea:focus{
    border-color:var(--blue);

    box-shadow:
        0 0 0 3px
        rgba(0,170,255,.07);
}

.textarea{
    min-height:125px;
    resize:vertical;
}

.row{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:12px;
}

/* BUTTONS */

.btn{
    border:none;

    border-radius:12px;

    padding:12px 18px;

    color:white;

    font-family:inherit;

    cursor:pointer;

    transition:.2s;

    font-size:11px;
}

.btn:hover{
    transform:translateY(-1px);
}

.btn-primary{
    background:
        linear-gradient(
            135deg,
            #00baff,
            #0876ff
        );

    box-shadow:
        0 8px 24px
        rgba(0,145,255,.18);
}

.btn-secondary{
    background:#132337;
    border:1px solid #21415d;
}

.btn-danger{
    background:#3a1624;
    color:#ff7b9a;
    border:1px solid #64283c;
}

.btn-green{
    background:
        linear-gradient(
            135deg,
            #12dca1,
            #0ba67d
        );
}

/* CHAT */

.chat-layout{
    display:grid;

    grid-template-columns:
        300px 1fr;

    gap:14px;
}

.chat-list{
    min-height:450px;
}

.chat-item{
    padding:13px;

    border:1px solid transparent;

    border-radius:13px;

    margin-bottom:7px;

    cursor:pointer;

    background:#0b1421;
}

.chat-item:hover,
.chat-item.selected{
    border-color:#1b5c7c;

    background:#0e2232;
}

.chat-item strong{
    display:block;
    font-size:11px;
}

.chat-item small{
    display:block;

    margin-top:5px;

    color:var(--muted);

    font-size:9px;

    direction:ltr;
    text-align:right;
}

.chat-window{
    min-height:450px;

    display:flex;
    flex-direction:column;
}

.messages{
    flex:1;

    background:
        radial-gradient(
            circle at center,
            rgba(0,180,255,.05),
            transparent 50%
        );

    border-radius:15px;

    border:1px solid #152a3e;

    padding:15px;

    min-height:300px;
}

.empty{
    height:100%;

    display:flex;

    align-items:center;

    justify-content:center;

    text-align:center;

    color:var(--muted);

    font-size:11px;
}

.send-box{
    display:flex;
    gap:8px;

    margin-top:12px;
}

/* COMMAND */

.command{
    display:flex;
    align-items:center;
    justify-content:space-between;

    padding:14px;

    border:1px solid var(--border);

    background:#0b1421;

    border-radius:13px;

    margin-bottom:8px;
}

.command-info strong{
    font-size:12px;
}

.command-info small{
    display:block;

    color:var(--muted);

    font-size:9px;

    margin-top:5px;
}

/* LOGIN */

.login-page{
    min-height:100vh;

    display:flex;

    align-items:center;

    justify-content:center;

    padding:20px;
}

.login-card{
    width:100%;
    max-width:440px;

    padding:28px;

    border:1px solid #1b3c56;

    border-radius:25px;

    background:
        radial-gradient(
            circle at top,
            rgba(0,180,255,.13),
            transparent 40%
        ),
        #09111d;

    box-shadow:
        0 30px 100px
        rgba(0,0,0,.4);
}

.login-logo{
    width:70px;
    height:70px;

    border-radius:22px;

    display:flex;

    align-items:center;
    justify-content:center;

    margin:0 auto 18px;

    font-size:34px;
    font-weight:900;

    color:#001019;

    background:
        linear-gradient(
            135deg,
            #00e0ff,
            #0078ff
        );

    box-shadow:
        0 0 45px
        rgba(0,200,255,.25);
}

.login-card h1{
    text-align:center;

    font-size:24px;

    margin-bottom:7px;
}

.login-card .sub{
    text-align:center;

    color:var(--muted);

    font-size:10px;

    margin-bottom:25px;
}

.error{
    color:#ff6f91;

    background:#321421;

    border:1px solid #5d263b;

    padding:11px;

    border-radius:10px;

    font-size:10px;

    margin-bottom:12px;

    display:none;
}

.success{
    color:#45e8b0;

    background:#0d2820;

    border:1px solid #1d624e;

    padding:11px;

    border-radius:10px;

    font-size:10px;

    margin-bottom:12px;

    display:none;
}

/* TOAST */

.toast{
    position:fixed;

    bottom:20px;
    left:20px;

    padding:13px 17px;

    border-radius:12px;

    background:#102032;

    border:1px solid #24506c;

    color:white;

    font-size:11px;

    transform:translateY(100px);

    opacity:0;

    transition:.3s;

    z-index:100;
}

.toast.show{
    transform:translateY(0);
    opacity:1;
}

/* MOBILE */

@media(max-width:900px){

    .sidebar{
        transform:translateX(270px);
        box-shadow:
            -20px 0 50px rgba(0,0,0,.35);
    }

    .sidebar.open{
        transform:translateX(0);
    }

    .content{
        margin-right:0;
        padding:15px;
    }

    .grid{
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }

    .chat-layout{
        grid-template-columns:1fr;
    }

}

@media(max-width:550px){

    .topbar{
        padding:0 12px;
    }

    .brand h1{
        font-size:14px;
    }

    .hero{
        padding:18px;
    }

    .hero h2{
        font-size:19px;
    }

    .grid{
        grid-template-columns:1fr 1fr;
        gap:9px;
    }

    .card{
        padding:13px;
        border-radius:15px;
    }

    .stat{
        min-height:105px;
    }

    .stat strong{
        font-size:19px;
    }

    .row{
        grid-template-columns:1fr;
    }

    .send-box{
        flex-direction:column;
    }

    .login-card{
        padding:22px;
    }

}

</style>

</head>

<body>

<div id="loginPage" class="login-page">

    <div class="login-card">

        <div class="login-logo">
            پ
        </div>

        <h1>پتی ربات‌ساز</h1>

        <p class="sub">
            پنل ساخت و مدیریت ربات روبیکا
        </p>

        <div id="loginError" class="error"></div>

        <div id="loginSuccess" class="success"></div>

        <div class="field">

            <label>
                توکن ربات
            </label>

            <input
                id="token"
                class="input"
                type="password"
                placeholder="توکن Bot API روبیکا را وارد کنید"
            >

        </div>

        <button
            class="btn btn-primary"
            style="width:100%;"
            onclick="connectBot()"
        >
            ورود به پنل ربات
        </button>

        <p
            style="
                color:#63768b;
                font-size:9px;
                line-height:2;
                text-align:center;
                margin-top:17px;
            "
        >
            توکن فقط برای اتصال ربات به پنل استفاده می‌شود.
        </p>

    </div>

</div>


<div id="app" class="app" style="display:none;">

    <!-- TOP BAR -->

    <header class="topbar">

        <div class="brand">

            <button
                class="menu-btn"
                onclick="toggleSidebar()"
            >
                ☰
            </button>

            <div class="logo">
                پ
            </div>

            <div>
                <h1>پتی ربات‌ساز</h1>
                <small>پنل مدیریت ربات روبیکا</small>
            </div>

        </div>

        <button
            class="btn btn-danger"
            onclick="logout()"
        >
            خروج
        </button>

    </header>


    <div class="layout">

        <!-- SIDEBAR -->

        <aside id="sidebar" class="sidebar">

            <div class="profile">

                <div class="profile-icon">
                    🤖
                </div>

                <strong id="botName">
                    ربات پتی
                </strong>

                <span id="botUsername">
                    در حال اتصال...
                </span>

            </div>

            <nav class="nav">

                <button
                    class="active"
                    onclick="showSection('dashboard',this)"
                >
                    <span class="nav-icon">⌂</span>
                    داشبورد
                </button>

                <button
                    onclick="showSection('start',this)"
                >
                    <span class="nav-icon">▶</span>
                    شروع ربات
                </button>

                <button
                    onclick="showSection('commands',this)"
                >
                    <span class="nav-icon">⚡</span>
                    دستورات
                </button>

                <button
                    onclick="showSection('chats',this)"
                >
                    <span class="nav-icon">☷</span>
                    چت‌ها
                </button>

                <button
                    onclick="showSection('keyboard',this)"
                >
                    <span class="nav-icon">▦</span>
                    کیبورد و دکمه‌ها
                </button>

                <button
                    onclick="showSection('console',this)"
                >
                    <span class="nav-icon">⌘</span>
                    کنسول
                </button>

                <button
                    onclick="showSection('settings',this)"
                >
                    <span class="nav-icon">⚙</span>
                    تنظیمات
                </button>

            </nav>

        </aside>


        <!-- CONTENT -->

        <main class="content">


            <!-- DASHBOARD -->

            <section
                id="dashboard"
                class="section active"
            >

                <div class="hero">

                    <div class="status">
                        <span class="status-dot"></span>
                        ربات متصل است
                    </div>

                    <h2>
                        پنل مدیریت پتی
                    </h2>

                    <p>
                        ربات خودت را از اینجا مدیریت کن،
                        دستور بساز، پیام ارسال کن و چت‌های
                        کاربران را به صورت خودکار دریافت کن.
                    </p>

                </div>


                <div class="grid">

                    <div class="card stat">

                        <div class="icon">
                            🤖
                        </div>

                        <strong id="statBot">
                            -
                        </strong>

                        <p>
                            وضعیت ربات
                        </p>

                    </div>


                    <div class="card stat">

                        <div class="icon">
                            👥
                        </div>

                        <strong id="statChats">
                            0
                        </strong>

                        <p>
                            چت‌های شناسایی‌شده
                        </p>

                    </div>


                    <div class="card stat">

                        <div class="icon">
                            ⚡
                        </div>

                        <strong id="statCommands">
                            2
                        </strong>

                        <p>
                            دستورات فعال
                        </p>

                    </div>


                    <div class="card stat">

                        <div class="icon">
                            ●
                        </div>

                        <strong>
                            Online
                        </strong>

                        <p>
                            وضعیت سرویس
                        </p>

                    </div>

                </div>


                <div class="title">

                    <h3>
                        دسترسی سریع
                    </h3>

                </div>


                <div class="grid">

                    <div
                        class="card"
                        onclick="goTo('start')"
                        style="cursor:pointer;"
                    >

                        <div class="icon">
                            ▶
                        </div>

                        <strong>
                            تنظیم شروع
                        </strong>

                        <p>
                            متن /start را تنظیم کن.
                        </p>

                    </div>


                    <div
                        class="card"
                        onclick="goTo('commands')"
                        style="cursor:pointer;"
                    >

                        <div class="icon">
                            ⚡
                        </div>

                        <strong>
                            ساخت دستور
                        </strong>

                        <p>
                            دستورهای جدید بساز.
                        </p>

                    </div>


                    <div
                        class="card"
                        onclick="goTo('chats')"
                        style="cursor:pointer;"
                    >

                        <div class="icon">
                            👥
                        </div>

                        <strong>
                            چت‌ها
                        </strong>

                        <p>
                            کاربران پیام‌دهنده را ببین.
                        </p>

                    </div>


                    <div
                        class="card"
                        onclick="goTo('console')"
                        style="cursor:pointer;"
                    >

                        <div class="icon">
                            ⌘
                        </div>

                        <strong>
                            ارسال پیام
                        </strong>

                        <p>
                            برای کاربر پیام بفرست.
                        </p>

                    </div>

                </div>

            </section>


            <!-- START -->

            <section
                id="start"
                class="section"
            >

                <div class="title">

                    <h3>
                        پیام شروع ربات
                    </h3>

                    <span>
                        /start
                    </span>

                </div>

                <div class="card form-card">

                    <div class="field">

                        <label>
                            متن خوش‌آمدگویی
                        </label>

                        <textarea
                            id="welcomeText"
                            class="textarea"
                        >سلام 👋 به ربات پتی خوش آمدید.</textarea>

                    </div>

                    <button
                        class="btn btn-primary"
                        onclick="saveWelcome()"
                    >
                        ذخیره تنظیمات
                    </button>

                </div>

            </section>


            <!-- COMMANDS -->

            <section
                id="commands"
                class="section"
            >

                <div class="title">

                    <h3>
                        دستورات ربات
                    </h3>

                    <span>
                        Commands
                    </span>

                </div>


                <div class="card form-card">

                    <div class="row">

                        <div class="field">

                            <label>
                                دستور
                            </label>

                            <input
                                id="commandName"
                                class="input"
                                placeholder="/about"
                            >

                        </div>


                        <div class="field">

                            <label>
                                عنوان
                            </label>

                            <input
                                id="commandTitle"
                                class="input"
                                placeholder="درباره ربات"
                            >

                        </div>

                    </div>


                    <div class="field">

                        <label>
                            پاسخ دستور
                        </label>

                        <textarea
                            id="commandResponse"
                            class="textarea"
                            placeholder="متن پاسخ..."
                        ></textarea>

                    </div>


                    <button
                        class="btn btn-primary"
                        onclick="addCommand()"
                    >
                        + افزودن دستور
                    </button>

                </div>


                <div class="title">
                    <h3>دستورهای ساخته‌شده</h3>
                </div>

                <div id="commandsList"></div>

            </section>


            <!-- CHATS -->

            <section
                id="chats"
                class="section"
            >

                <div class="title">

                    <h3>
                        چت‌های کاربران
                    </h3>

                    <span>
                        chat_id به صورت خودکار
                    </span>

                </div>


                <div class="chat-layout">

                    <div class="card chat-list">

                        <div
                            id="chatList"
                        >
                            <div class="empty">
                                هنوز کاربری به ربات پیام نداده است.
                            </div>
                        </div>

                    </div>


                    <div class="card chat-window">

                        <div class="messages">

                            <div
                                id="selectedChat"
                                class="empty"
                            >
                                یک چت را انتخاب کنید.
                            </div>

                        </div>

                        <div class="send-box">

                            <input
                                id="chatMessage"
                                class="input"
                                placeholder="پیام را بنویسید..."
                            >

                            <button
                                class="btn btn-primary"
                                onclick="sendSelectedMessage()"
                            >
                                ارسال
                            </button>

                        </div>

                    </div>

                </div>

            </section>


            <!-- KEYBOARD -->

            <section
                id="keyboard"
                class="section"
            >

                <div class="title">

                    <h3>
                        کیبورد و دکمه‌ها
                    </h3>

                    <span>
                        طراحی پنل
                    </span>

                </div>


                <div class="card form-card">

                    <div class="field">

                        <label>
                            عنوان دکمه
                        </label>

                        <input
                            class="input"
                            placeholder="مثلاً درباره پتی"
                        >

                    </div>

                    <div class="row">

                        <button
                            class="btn btn-primary"
                        >
                            + افزودن دکمه
                        </button>

                        <button
                            class="btn btn-secondary"
                        >
                            ذخیره کیبورد
                        </button>

                    </div>

                    <div
                        style="
                            margin-top:20px;
                            padding:15px;
                            border:1px dashed #21415d;
                            border-radius:14px;
                            text-align:center;
                            color:#71849a;
                            font-size:10px;
                        "
                    >
                        پیش‌نمایش کیبورد ربات
                    </div>

                </div>

            </section>


            <!-- CONSOLE -->

            <section
                id="console"
                class="section"
            >

                <div class="title">

                    <h3>
                        کنسول ارسال پیام
                    </h3>

                    <span>
                        Send Message
                    </span>

                </div>


                <div class="card form-card">

                    <div class="field">

                        <label>
                            Chat ID
                        </label>

                        <input
                            id="consoleChatId"
                            class="input"
                            placeholder="با انتخاب کاربر خودکار پر می‌شود"
                        >

                    </div>


                    <div class="field">

                        <label>
                            متن پیام
                        </label>

                        <textarea
                            id="consoleText"
                            class="textarea"
                            placeholder="پیام..."
                        ></textarea>

                    </div>


                    <button
                        class="btn btn-green"
                        onclick="sendConsoleMessage()"
                    >
                        ارسال پیام
                    </button>

                </div>

            </section>


            <!-- SETTINGS -->

            <section
                id="settings"
                class="section"
            >

                <div class="title">

                    <h3>
                        تنظیمات
                    </h3>

                </div>


                <div class="card form-card">

                    <div class="field">

                        <label>
                            توکن فعلی
                        </label>

                        <input
                            id="tokenView"
                            class="input"
                            type="password"
                            readonly
                        >

                    </div>


                    <button
                        class="btn btn-danger"
                        onclick="logout()"
                    >
                        قطع اتصال ربات
                    </button>

                </div>

            </section>

        </main>

    </div>

</div>


<div
    id="toast"
    class="toast"
></div>


<script>

let selectedChatId = null;


/* =========================================================
   HELPERS
========================================================= */

function toast(message){

    const el =
        document.getElementById("toast");

    el.textContent = message;

    el.classList.add("show");

    setTimeout(() => {
        el.classList.remove("show");
    }, 2500);
}


async function api(url, options={}){

    const response =
        await fetch(url, {
            headers:{
                "Content-Type":
                    "application/json"
            },
            ...options
        });

    return response.json();
}


/* =========================================================
   LOGIN
========================================================= */

async function connectBot(){

    const token =
        document
        .getElementById("token")
        .value
        .trim();

    const error =
        document.getElementById(
            "loginError"
        );

    const success =
        document.getElementById(
            "loginSuccess"
        );

    error.style.display = "none";
    success.style.display = "none";

    if(!token){

        error.textContent =
            "توکن ربات را وارد کنید.";

        error.style.display = "block";

        return;
    }

    success.textContent =
        "در حال اتصال به روبیکا...";

    success.style.display = "block";

    try{

        const result =
            await api(
                "/api/connect",
                {
                    method:"POST",
                    body:JSON.stringify({
                        token:token
                    })
                }
            );

        if(!result.ok){

            error.textContent =
                result.message ||
                "اتصال ناموفق بود.";

            error.style.display =
                "block";

            success.style.display =
                "none";

            return;
        }

        localStorage.setItem(
            "peti_token",
            token
        );

        document.getElementById(
            "loginPage"
        ).style.display = "none";

        document.getElementById(
            "app"
        ).style.display = "block";

        document.getElementById(
            "tokenView"
        ).value = token;

        updateBotInfo(
            result.bot || {}
        );

        loadData();

        toast(
            "ربات با موفقیت متصل شد."
        );

    }catch(e){

        error.textContent =
            "خطا در ارتباط با سرور.";

        error.style.display =
            "block";

        success.style.display =
            "none";
    }
}


function updateBotInfo(bot){

    const name =
        bot.name ||
        bot.username ||
        bot.first_name ||
        "ربات پتی";

    const username =
        bot.username ||
        bot.user_name ||
        "ربات متصل";

    document.getElementById(
        "botName"
    ).textContent = name;

    document.getElementById(
        "botUsername"
    ).textContent =
        username;

    document.getElementById(
        "statBot"
    ).textContent =
        "Online";
}


/* =========================================================
   AUTO LOGIN
========================================================= */

window.addEventListener(
    "load",
    async () => {

        const token =
            localStorage.getItem(
                "peti_token"
            );

        if(!token)
            return;

        document.getElementById(
            "token"
        ).value = token;

        try{

            const result =
                await api(
                    "/api/connect",
                    {
                        method:"POST",
                        body:JSON.stringify({
                            token:token
                        })
                    }
                );

            if(result.ok){

                document.getElementById(
                    "loginPage"
                ).style.display =
                    "none";

                document.getElementById(
                    "app"
                ).style.display =
                    "block";

                document.getElementById(
                    "tokenView"
                ).value =
                    token;

                updateBotInfo(
                    result.bot || {}
                );

                loadData();
            }

        }catch(e){}

    }
);


/* =========================================================
   NAVIGATION
========================================================= */

function toggleSidebar(){

    document
        .getElementById("sidebar")
        .classList.toggle("open");
}


function showSection(id, button){

    document
        .querySelectorAll(".section")
        .forEach(el => {
            el.classList.remove(
                "active"
            );
        });

    const section =
        document.getElementById(id);

    if(section)
        section.classList.add(
            "active"
        );

    document
        .querySelectorAll(".nav button")
        .forEach(el => {
            el.classList.remove(
                "active"
            );
        });

    if(button)
        button.classList.add(
            "active"
        );

    document
        .getElementById("sidebar")
        .classList.remove("open");

    if(id === "chats"){
        loadData();
    }
}


function goTo(id){

    const buttons =
        document.querySelectorAll(
            ".nav button"
        );

    let button = null;

    buttons.forEach(btn => {

        if(
            btn.textContent
            .includes(
                id === "start"
                ? "شروع"
                : id === "commands"
                ? "دستورات"
                : id === "chats"
                ? "چت‌ها"
                : id === "console"
                ? "کنسول"
                : ""
            )
        ){
            button = btn;
        }

    });

    showSection(
        id,
        button
    );
}


/* =========================================================
   LOAD DATA
========================================================= */

async function loadData(){

    try{

        const data =
            await api(
                "/api/status"
            );

        if(!data)
            return;

        document.getElementById(
            "statChats"
        ).textContent =
            (data.chats || []).length;

        document.getElementById(
            "statCommands"
        ).textContent =
            2 +
            Object.keys(
                data.commands || {}
            ).length;

        renderChats(
            data.chats || []
        );

        renderCommands(
            data.commands || {}
        );

        document.getElementById(
            "welcomeText"
        ).value =
            data.welcome ||
            "سلام 👋 به ربات پتی خوش آمدید.";

    }catch(e){}

}


/* =========================================================
   CHATS
========================================================= */

function renderChats(chats){

    const box =
        document.getElementById(
            "chatList"
        );

    if(!chats.length){

        box.innerHTML = `
            <div class="empty">
                هنوز کاربری به ربات پیام نداده است.
                <br><br>
                یک پیام برای ربات بفرستید.
            </div>
        `;

        return;
    }

    box.innerHTML = "";

    chats
        .slice()
        .reverse()
        .forEach(chat => {

            const div =
                document.createElement(
                    "div"
                );

            div.className =
                "chat-item";

            div.onclick = () =>
                selectChat(chat.chat_id);

            div.innerHTML = `
                <strong>
                    ${escapeHtml(
                        chat.title ||
                        "کاربر"
                    )}
                </strong>

                <small>
                    ${escapeHtml(
                        chat.chat_id
                    )}
                </small>

                <small>
                    ${escapeHtml(
                        chat.last_message ||
                        ""
                    )}
                </small>
            `;

            box.appendChild(div);
        });
}


function selectChat(chatId){

    selectedChatId =
        chatId;

    document.getElementById(
        "consoleChatId"
    ).value =
        chatId;

    const chat =
        document.querySelector(
            `#chatList .chat-item`
        );

    document.getElementById(
        "selectedChat"
    ).innerHTML = `
        <div style="
            width:100%;
            text-align:right;
        ">

            <div style="
                padding:14px;
                background:#0b1928;
                border:1px solid #17364e;
                border-radius:14px;
            ">

                <strong>
                    چت انتخاب شد
                </strong>

                <div style="
                    color:#00cfff;
                    direction:ltr;
                    text-align:right;
                    margin-top:8px;
                    font-size:11px;
                ">
                    ${escapeHtml(chatId)}
                </div>

                <div style="
                    color:#73869b;
                    margin-top:10px;
                    font-size:10px;
                ">
                    اکنون می‌توانید پیام ارسال کنید.
                </div>

            </div>

        </div>
    `;

    toast(
        "چت انتخاب شد."
    );
}


async function sendSelectedMessage(){

    if(!selectedChatId){

        toast(
            "ابتدا یک چت انتخاب کنید."
        );

        return;
    }

    const input =
        document.getElementById(
            "chatMessage"
        );

    const text =
        input.value.trim();

    if(!text)
        return;

    const result =
        await api(
            "/api/send",
            {
                method:"POST",
                body:JSON.stringify({
                    chat_id:
                        selectedChatId,
                    text:text
                })
            }
        );

    if(result.ok){

        input.value = "";

        toast(
            "پیام ارسال شد."
        );

    }else{

        toast(
            "ارسال پیام ناموفق بود."
        );
    }
}


/* =========================================================
   WELCOME
========================================================= */

async function saveWelcome(){

    const text =
        document.getElementById(
            "welcomeText"
        ).value;

    const result =
        await api(
            "/api/welcome",
            {
                method:"POST",
                body:JSON.stringify({
                    text:text
                })
            }
        );

    if(result.ok)
        toast(
            "پیام شروع ذخیره شد."
        );
}


/* =========================================================
   COMMANDS
========================================================= */

async function addCommand(){

    const command =
        document.getElementById(
            "commandName"
        ).value.trim();

    const title =
        document.getElementById(
            "commandTitle"
        ).value.trim();

    const response =
        document.getElementById(
            "commandResponse"
        ).value.trim();

    if(!command){

        toast(
            "نام دستور را وارد کنید."
        );

        return;
    }

    const result =
        await api(
            "/api/command",
            {
                method:"POST",
                body:JSON.stringify({
                    command:command,
                    title:title,
                    response:response
                })
            }
        );

    if(result.ok){

        document.getElementById(
            "commandName"
        ).value = "";

        document.getElementById(
            "commandTitle"
        ).value = "";

        document.getElementById(
            "commandResponse"
        ).value = "";

        toast(
            "دستور اضافه شد."
        );

        loadData();
    }
}


function renderCommands(commands){

    const box =
        document.getElementById(
            "commandsList"
        );

    box.innerHTML = "";

    Object.entries(
        commands || {}
    ).forEach(
        ([command, info]) => {

            const div =
                document.createElement(
                    "div"
                );

            div.className =
                "command";

            div.innerHTML = `

                <div class="command-info">

                    <strong>
                        ${escapeHtml(command)}
                    </strong>

                    <small>
                        ${escapeHtml(
                            info.title || ""
                        )}
                    </small>

                </div>

                <button
                    class="btn btn-danger"
                    onclick="deleteCommand(
                        '${escapeJs(command)}'
                    )"
                >
                    حذف
                </button>

            `;

            box.appendChild(div);
        }
    );
}


async function deleteCommand(command){

    await api(
        "/api/command/" +
        encodeURIComponent(command),
        {
            method:"DELETE"
        }
    );

    toast(
        "دستور حذف شد."
    );

    loadData();
}


/* =========================================================
   CONSOLE
========================================================= */

async function sendConsoleMessage(){

    const chatId =
        document.getElementById(
            "consoleChatId"
        ).value.trim();

    const text =
        document.getElementById(
            "consoleText"
        ).value.trim();

    if(!chatId){

        toast(
            "Chat ID را وارد یا انتخاب کنید."
        );

        return;
    }

    if(!text)
        return;

    const result =
        await api(
            "/api/send",
            {
                method:"POST",
                body:JSON.stringify({
                    chat_id:chatId,
                    text:text
                })
            }
        );

    if(result.ok){

        document.getElementById(
            "consoleText"
        ).value = "";

        toast(
            "پیام ارسال شد."
        );

    }else{

        toast(
            "ارسال پیام ناموفق بود."
        );
    }
}


/* =========================================================
   LOGOUT
========================================================= */

function logout(){

    localStorage.removeItem(
        "peti_token"
    );

    location.reload();
}


/* =========================================================
   ESCAPE
========================================================= */

function escapeHtml(value){

    return String(value)
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");
}


function escapeJs(value){

    return String(value)
        .replaceAll("\\","\\\\")
        .replaceAll("'","\\'");
}


/* =========================================================
   AUTO REFRESH
========================================================= */

setInterval(
    () => {

        const app =
            document.getElementById(
                "app"
            );

        if(
            app &&
            app.style.display !== "none"
        ){
            loadData();
        }

    },
    3000
);

</script>

</body>
</html>
"""


# ============================================================
# MAIN PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(HTML)


# ============================================================
# RENDER ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
        )
