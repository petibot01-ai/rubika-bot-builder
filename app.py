import os
import sqlite3
import threading
import time
from typing import Optional, Any

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# =========================================================
# PETI BOT BUILDER
# ربات ساز پتی - نسخه یک فایل
# Render Ready / Persian RTL / Rubika Bot API
# =========================================================

app = FastAPI(title="Peti Bot Builder")

API_BASE = "https://botapi.rubika.ir/v3"
DB_PATH = os.environ.get("PETI_DB", "peti.db")

db_lock = threading.Lock()
worker_lock = threading.Lock()

worker_started = False
active_token = ""
bot_info: dict[str, Any] = {}
last_update_offset: Optional[str] = None


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = db()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                last_text TEXT DEFAULT '',
                updated_at INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)

        conn.commit()
        conn.close()


def upsert_chat(
    chat_id,
    name="",
    username="",
    text=""
):
    now = int(time.time())

    with db_lock:
        conn = db()

        old = conn.execute(
            "SELECT messages FROM chats WHERE chat_id=?",
            (str(chat_id),)
        ).fetchone()

        count = (old["messages"] if old else 0) + 1

        conn.execute("""
            INSERT INTO chats(
                chat_id,
                name,
                username,
                last_text,
                updated_at,
                messages
            )
            VALUES(?,?,?,?,?,?)

            ON CONFLICT(chat_id) DO UPDATE SET
                name=CASE
                    WHEN excluded.name <> ''
                    THEN excluded.name
                    ELSE chats.name
                END,

                username=CASE
                    WHEN excluded.username <> ''
                    THEN excluded.username
                    ELSE chats.username
                END,

                last_text=excluded.last_text,
                updated_at=excluded.updated_at,
                messages=excluded.messages
        """, (
            str(chat_id),
            name or "",
            username or "",
            text or "",
            now,
            count
        ))

        conn.commit()
        conn.close()


def get_chats():
    with db_lock:
        conn = db()

        rows = conn.execute(
            """
            SELECT *
            FROM chats
            ORDER BY updated_at DESC
            """
        ).fetchall()

        conn.close()

    return [dict(row) for row in rows]


def save_setting(key, value):
    with db_lock:
        conn = db()

        conn.execute("""
            INSERT INTO settings(key,value)
            VALUES(?,?)

            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
        """, (
            key,
            value
        ))

        conn.commit()
        conn.close()


def read_setting(key, default=""):
    with db_lock:
        conn = db()

        row = conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        ).fetchone()

        conn.close()

    if row:
        return row["value"]

    return default


init_db()


# =========================================================
# RUBIKA API
# =========================================================

def rubika_request(
    token: str,
    method: str,
    data=None
):
    token = token.strip()

    if not token:
        raise ValueError("توکن خالی است.")

    url = f"{API_BASE}/{token}/{method}"

    response = requests.post(
        url,
        json=data or {},
        headers={
            "Content-Type": "application/json"
        },
        timeout=30
    )

    try:
        payload = response.json()

    except Exception:
        raise RuntimeError(
            f"پاسخ نامعتبر از روبیکا - HTTP {response.status_code}"
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}: {payload}"
        )

    return payload


def get_me(token):
    return rubika_request(
        token,
        "getMe",
        {}
    )


def get_updates(
    token,
    offset_id=None
):
    data = {
        "limit": 50
    }

    if offset_id:
        data["offset_id"] = offset_id

    return rubika_request(
        token,
        "getUpdates",
        data
    )


def send_message(
    token,
    chat_id,
    text
):
    return rubika_request(
        token,
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": str(text)
        }
    )


# =========================================================
# UPDATE PARSER
# =========================================================

def find_first(obj, keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        value = obj.get(key)

        if value not in (None, ""):
            return value

    return None


def extract_chat_id(update):
    if not isinstance(update, dict):
        return None

    value = find_first(
        update,
        [
            "chat_id",
            "chatId",
            "object_guid",
            "objectGuid"
        ]
    )

    if value:
        return str(value)

    for key in (
        "new_message",
        "message",
        "updated_message",
        "inline_message"
    ):
        value = extract_chat_id(
            update.get(key)
        )

        if value:
            return value

    return None


def extract_text(update):
    if not isinstance(update, dict):
        return ""

    value = find_first(
        update,
        [
            "text",
            "message_text"
        ]
    )

    if value is not None:
        return str(value)

    for key in (
        "new_message",
        "message",
        "updated_message"
    ):
        value = extract_text(
            update.get(key)
        )

        if value:
            return value

    return ""


def extract_sender(update):
    if not isinstance(update, dict):
        return "", ""

    candidates = [
        update.get("sender"),
        update.get("user"),
        update.get("from"),
        update.get("author")
    ]

    for obj in candidates:

        if isinstance(obj, dict):

            name = find_first(
                obj,
                [
                    "first_name",
                    "name",
                    "display_name",
                    "username",
                    "user_name"
                ]
            ) or ""

            username = find_first(
                obj,
                [
                    "username",
                    "user_name"
                ]
            ) or ""

            if name or username:
                return (
                    str(name),
                    str(username)
                )

    for key in (
        "new_message",
        "message"
    ):

        name, username = extract_sender(
            update.get(key)
        )

        if name or username:
            return name, username

    return "", ""


def update_list(payload):
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")

    if isinstance(data, dict):

        for key in (
            "updates",
            "update",
            "items"
        ):

            if isinstance(
                data.get(key),
                list
            ):
                return data[key]

    for key in (
        "updates",
        "update",
        "items"
    ):

        if isinstance(
            payload.get(key),
            list
        ):
            return payload[key]

    return []


def next_offset(payload):

    if not isinstance(payload, dict):
        return None

    data = payload.get("data")

    if isinstance(data, dict):

        value = (
            data.get("next_offset_id")
            or data.get("next_offset")
        )

        if value:
            return str(value)

    value = (
        payload.get("next_offset_id")
        or payload.get("next_offset")
    )

    if value:
        return str(value)

    return None


# =========================================================
# BOT WORKER
# =========================================================

def bot_worker(token):

    global last_update_offset
    global bot_info

    print("[Peti] worker started")

    while True:

        try:

            payload = get_updates(
                token,
                last_update_offset
            )

            offset = next_offset(payload)

            if offset:
                last_update_offset = offset

            updates = update_list(payload)

            for update in updates:

                chat_id = extract_chat_id(update)

                if not chat_id:
                    continue

                text = extract_text(update)

                name, username = extract_sender(
                    update
                )

                upsert_chat(
                    chat_id=chat_id,
                    name=name,
                    username=username,
                    text=text
                )

                print(
                    f"[Peti] New message "
                    f"chat={chat_id} "
                    f"text={text}"
                )

                # -----------------------------------------
                # /start
                # -----------------------------------------

                if text.strip() == "/start":

                    start_text = read_setting(
                        "start_message",
                        "سلام 👋\nبه ربات پتی خوش آمدید.\nچت شما خودکار شناسایی شد."
                    )

                    try:

                        send_message(
                            token,
                            chat_id,
                            start_text
                        )

                    except Exception as error:

                        print(
                            "[Peti] start reply error:",
                            error
                        )

                # -----------------------------------------
                # /help
                # -----------------------------------------

                elif text.strip() == "/help":

                    try:

                        send_message(
                            token,
                            chat_id,
                            "🤖 راهنمای پتی\n\n/start شروع\n/help راهنما"
                        )

                    except Exception as error:

                        print(
                            "[Peti] help error:",
                            error
                        )

            time.sleep(1)

        except Exception as error:

            print(
                "[Peti] worker error:",
                repr(error)
            )

            time.sleep(5)


def start_worker(token):

    global worker_started
    global active_token

    with worker_lock:

        if (
            worker_started
            and active_token == token
        ):
            return

        active_token = token
        worker_started = True

        thread = threading.Thread(
            target=bot_worker,
            args=(token,),
            daemon=True
        )

        thread.start()


# =========================================================
# MODELS
# =========================================================

class TokenRequest(BaseModel):
    token: str


class SendRequest(BaseModel):
    token: str
    chat_id: str
    text: str


class StartMessageRequest(BaseModel):
    token: str
    text: str


# =========================================================
# API ROUTES
# =========================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "Peti Bot Builder"
    }


@app.post("/api/connect")
def connect(req: TokenRequest):

    global bot_info

    token = req.token.strip()

    if not token:

        return {
            "ok": False,
            "message": "توکن را وارد کنید."
        }

    try:

        result = get_me(token)

        bot_info = result.get(
            "data",
            result
        )

        save_setting(
            "bot_connected",
            "1"
        )

        start_worker(token)

        return {
            "ok": True,
            "message": "ربات با موفقیت متصل شد.",
            "bot": bot_info
        }

    except Exception as error:

        return {
            "ok": False,
            "message": str(error)
        }


@app.get("/api/chats")
def chats(token: str):

    return {
        "ok": True,
        "chats": get_chats()
    }


@app.post("/api/send")
def send(req: SendRequest):

    if not req.token.strip():

        return {
            "ok": False,
            "message": "توکن خالی است."
        }

    if not req.chat_id.strip():

        return {
            "ok": False,
            "message": "یک چت را انتخاب کنید."
        }

    if not req.text.strip():

        return {
            "ok": False,
            "message": "متن پیام خالی است."
        }

    try:

        result = send_message(
            req.token,
            req.chat_id,
            req.text
        )

        upsert_chat(
            req.chat_id,
            text="پیام ارسال‌شده: " + req.text
        )

        return {
            "ok": True,
            "result": result
        }

    except Exception as error:

        return {
            "ok": False,
            "message": str(error)
        }


@app.post("/api/start-message")
def start_message(
    req: StartMessageRequest
):

    save_setting(
        "start_message",
        req.text
    )

    return {
        "ok": True,
        "message": "متن شروع ذخیره شد."
    }


@app.get("/api/settings")
def settings():

    return {
        "ok": True,
        "start_message": read_setting(
            "start_message",
            "سلام 👋 به ربات پتی خوش آمدید."
        )
    }


# =========================================================
# HTML / UI
# =========================================================

HTML = r"""
<!doctype html>

<html lang="fa" dir="rtl">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
پتی | ربات‌ساز روبیکا
</title>

<style>

:root{

    --bg:#030918;

    --panel:#071126;

    --panel2:#09162d;

    --line:#12304b;

    --cyan:#13d8ff;

    --blue:#347dff;

    --text:#eef7ff;

    --muted:#7e94b7;

    --green:#31e6a0;

    --danger:#ff6685;

    --shadow:
        0 18px 55px rgba(0,0,0,.35);

}

*{
    box-sizing:border-box;
}

html,
body{

    margin:0;

    background:var(--bg);

    color:var(--text);

    font-family:
        Tahoma,
        Arial,
        sans-serif;

}

body{

    background-image:

        radial-gradient(
            circle at 78% 12%,
            rgba(22,170,255,.13),
            transparent 24%
        ),

        linear-gradient(
            rgba(16,58,91,.13) 1px,
            transparent 1px
        ),

        linear-gradient(
            90deg,
            rgba(16,58,91,.13) 1px,
            transparent 1px
        );

    background-size:
        auto,
        52px 52px,
        52px 52px;

    min-height:100vh;

}

button,
input,
textarea{

    font:inherit;

}

button{

    cursor:pointer;

}

.hidden{

    display:none!important;

}

#app{

    min-height:100vh;

}


/* TOPBAR */

.topbar{

    height:76px;

    position:sticky;

    top:0;

    z-index:20;

    background:
        rgba(3,9,24,.88);

    backdrop-filter:
        blur(18px);

    border-bottom:
        1px solid
        rgba(19,216,255,.13);

    display:flex;

    align-items:center;

    justify-content:space-between;

    padding:0 20px;

}

.brand{

    display:flex;

    align-items:center;

    gap:12px;

    font-size:24px;

    font-weight:900;

    color:#18bfff;

}

.brandIcon{

    width:48px;

    height:48px;

    border-radius:15px;

    display:grid;

    place-items:center;

    background:
        linear-gradient(
            135deg,
            #10dfff,
            #3579ff
        );

    box-shadow:
        0 0 30px
        rgba(19,216,255,.35);

    color:#fff;

}

.top-actions{

    display:flex;

    align-items:center;

    gap:9px;

}

.pill{

    border:
        1px solid #173f55;

    background:#07172a;

    border-radius:30px;

    padding:9px 13px;

    color:#9cb1cc;

    font-size:13px;

}

.dot{

    width:9px;

    height:9px;

    background:var(--green);

    display:inline-block;

    border-radius:50%;

    box-shadow:
        0 0 14px
        var(--green);

}


/* LAYOUT */

.layout{

    display:flex;

    min-height:
        calc(100vh - 76px);

}

.sidebar{

    width:260px;

    flex:none;

    border-left:
        1px solid
        rgba(19,216,255,.10);

    background:
        rgba(4,13,30,.82);

    padding:20px 14px;

}

.nav-title{

    font-size:11px;

    color:#516985;

    padding:
        12px 12px 8px;

}

.nav{

    width:100%;

    border:
        1px solid transparent;

    background:transparent;

    color:#8da4c2;

    padding:13px 14px;

    border-radius:14px;

    text-align:right;

    margin:3px 0;

    display:flex;

    gap:11px;

    align-items:center;

}

.nav:hover,
.nav.active{

    background:
        linear-gradient(
            90deg,
            rgba(16,216,255,.10),
            rgba(55,121,255,.12)
        );

    color:#fff;

    border-color:#143c55;

}

.nav b{

    font-size:17px;

    width:22px;

}

.main{

    flex:1;

    padding:24px;

    max-width:1400px;

    margin:auto;

    width:100%;

}


/* HERO */

.hero{

    background:
        linear-gradient(
            135deg,
            rgba(12,39,72,.82),
            rgba(5,17,37,.82)
        );

    border:
        1px solid #123958;

    border-radius:26px;

    padding:27px;

    box-shadow:var(--shadow);

    position:relative;

    overflow:hidden;

}

.hero:after{

    content:"";

    position:absolute;

    width:260px;

    height:260px;

    border-radius:50%;

    left:-100px;

    top:-100px;

    background:
        rgba(19,216,255,.07);

    filter:blur(4px);

}

.hero h1{

    margin:
        0 0 10px;

    font-size:32px;

}

.hero h1 span{

    color:#19cfff;

}

.hero p{

    margin:0;

    color:#8199ba;

    line-height:2;

}


/* STATS */

.grid4{

    display:grid;

    grid-template-columns:
        repeat(4,1fr);

    gap:14px;

    margin-top:16px;

}

.stat{

    background:
        rgba(7,20,42,.86);

    border:
        1px solid #12304a;

    border-radius:20px;

    padding:18px;

    box-shadow:var(--shadow);

}

.stat .ico{

    font-size:26px;

    margin-bottom:12px;

}

.stat .num{

    font-size:28px;

    font-weight:900;

}

.stat .label{

    color:#7890ae;

    margin-top:5px;

}


/* SECTIONS */

.section-title{

    display:flex;

    align-items:center;

    justify-content:space-between;

    margin:26px 0 12px;

}

.section-title h2{

    font-size:20px;

    margin:0;

}

.section-title span{

    color:#68809f;

    font-size:12px;

}

.grid3{

    display:grid;

    grid-template-columns:
        repeat(3,1fr);

    gap:16px;

}

.card{

    background:
        linear-gradient(
            180deg,
            rgba(8,21,44,.95),
            rgba(5,15,31,.95)
        );

    border:
        1px solid #12314c;

    border-radius:24px;

    padding:22px;

    box-shadow:var(--shadow);

}

.feature{

    min-height:180px;

    display:flex;

    flex-direction:column;

    align-items:center;

    text-align:center;

    justify-content:center;

}

.feature .bigicon{

    width:72px;

    height:72px;

    border-radius:22px;

    display:grid;

    place-items:center;

    background:
        linear-gradient(
            145deg,
            #0a2d48,
            #0a1a32
        );

    border:
        1px solid #075b76;

    color:#1cdbff;

    font-size:31px;

    margin-bottom:13px;

}

.feature h3{

    margin:
        4px 0 7px;

    font-size:18px;

}

.feature p{

    margin:0;

    color:#738bad;

    font-size:13px;

    line-height:1.8;

}


/* VIEWS */

.view{

    display:none;

}

.view.active{

    display:block;

}


/* FORM */

.field{

    margin:12px 0;

}

.field label{

    display:block;

    color:#8da4c2;

    margin-bottom:7px;

    font-size:13px;

}

.input,
.textarea{

    width:100%;

    background:#040d1d;

    border:
        1px solid #163852;

    color:#fff;

    border-radius:14px;

    padding:13px;

    outline:none;

}

.input:focus,
.textarea:focus{

    border-color:#14d7ff;

    box-shadow:
        0 0 0 3px
        rgba(19,216,255,.07);

}

.textarea{

    min-height:120px;

    resize:vertical;

}


/* BUTTON */

.btn{

    border:0;

    border-radius:14px;

    padding:12px 17px;

    background:
        linear-gradient(
            135deg,
            #10cfe8,
            #377cff
        );

    color:#fff;

    font-weight:800;

    box-shadow:
        0 10px 25px
        rgba(28,128,255,.18);

}

.btn.secondary{

    background:#0b1d34;

    border:
        1px solid #1a3e59;

    color:#b8cbe1;

    box-shadow:none;

}

.btn.danger{

    background:#321526;

    color:#ff9eb3;

}

.btn.full{

    width:100%;

}

.toolbar{

    display:flex;

    gap:9px;

    flex-wrap:wrap;

}


/* LOGIN */

.login-wrap{

    min-height:100vh;

    display:grid;

    place-items:center;

    padding:22px;

}

.login-card{

    width:min(520px,100%);

    padding:34px;

    border-radius:30px;

    background:
        rgba(6,16,36,.94);

    border:
        1px solid #143c59;

    box-shadow:
        0 30px 90px
        rgba(0,0,0,.5);

    text-align:center;

}

.lock{

    width:90px;

    height:90px;

    margin:
        0 auto 18px;

    border-radius:27px;

    display:grid;

    place-items:center;

    color:#16dcff;

    font-size:42px;

    background:#08203a;

    border:
        1px solid #0b536c;

    box-shadow:
        0 0 35px
        rgba(19,216,255,.12);

}

.login-card h1{

    margin:0 0 8px;

    color:#19cfff;

}

.login-card p{

    color:#778eae;

    line-height:2;

}

.alert{

    margin-top:12px;

    padding:12px;

    border-radius:12px;

    background:#081a2b;

    color:#88a0bc;

    font-size:13px;

}

.alert.ok{

    color:#51e9aa;

}

.alert.err{

    color:#ff718b;

}


/* TABLE */

.table{

    width:100%;

    border-collapse:collapse;

}

.table th,
.table td{

    padding:13px;

    border-bottom:
        1px solid #12283f;

    text-align:right;

}

.table th{

    color:#6e86a4;

    font-size:12px;

}

.table td{

    font-size:13px;

}


/* CHAT */

.chatlist{

    display:grid;

    gap:9px;

}

.chat{

    display:flex;

    align-items:center;

    justify-content:space-between;

    gap:10px;

    padding:14px;

    border-radius:16px;

    background:#07172a;

    border:
        1px solid #13334c;

    cursor:pointer;

}

.chat:hover,
.chat.sel{

    border-color:#13d8ff;

    background:#0a2035;

}

.chat-main{

    min-width:0;

}

.chat-name{

    font-weight:800;

}

.chat-id{

    font-size:11px;

    color:#5f7895;

    direction:ltr;

    text-align:right;

}

.chat-last{

    font-size:12px;

    color:#7189a7;

    white-space:nowrap;

    overflow:hidden;

    text-overflow:ellipsis;

    margin-top:5px;

}

.badge{

    font-size:11px;

    color:#54e9ac;

    background:#062b28;

    padding:5px 8px;

    border-radius:20px;

}


/* CONSOLE */

.console{

    background:#020811;

    border:
        1px solid #12314a;

    border-radius:16px;

    padding:15px;

    min-height:300px;

    color:#76f2c0;

    font-family:monospace;

    white-space:pre-wrap;

    overflow:auto;

}


/* SWITCH */

.switch{

    display:inline-flex;

    align-items:center;

    gap:10px;

    color:#4ce7a8;

}

.switch input{

    display:none;

}

.slider{

    width:48px;

    height:26px;

    border-radius:20px;

    background:#25354a;

    position:relative;

}

.slider:after{

    content:"";

    position:absolute;

    width:20px;

    height:20px;

    top:3px;

    right:4px;

    border-radius:50%;

    background:#788da7;

    transition:.2s;

}

.switch input:checked+.slider{

    background:#075c4a;

}

.switch input:checked+.slider:after{

    right:24px;

    background:#31e6a0;

}


/* MOBILE */

@media(max-width:900px){

    .sidebar{

        position:fixed;

        right:-280px;

        top:76px;

        height:
            calc(100vh - 76px);

        z-index:30;

        transition:.25s;

    }

    .sidebar.open{

        right:0;

    }

    .grid4{

        grid-template-columns:
            repeat(2,1fr);

    }

    .grid3{

        grid-template-columns:
            1fr 1fr;

    }

    .main{

        padding:15px;

    }

    .menuBtn{

        display:block!important;

    }

}

@media(max-width:600px){

    .grid4,
    .grid3{

        grid-template-columns:1fr;

    }

    .hero h1{

        font-size:25px;

    }

    .topbar{

        padding:0 11px;

    }

    .brand{

        font-size:20px;

    }

    .main{

        padding:11px;

    }

    .card,
    .hero{

        border-radius:20px;

        padding:17px;

    }

}

.menuBtn{

    display:none;

    border:
        1px solid #123c56;

    background:#081a2c;

    color:#17d9ff;

    border-radius:12px;

    padding:9px 12px;

}

</style>

</head>


<body>


<!-- =====================================================
LOGIN
===================================================== -->

<div id="login" class="login-wrap">

    <div class="login-card">

        <div class="lock">
            🔐
        </div>

        <h1>
            ورود به پنل پتی
        </h1>

        <p>
            توکن ربات روبیکا را وارد کنید
            تا پنل مدیریت ربات فعال شود.
        </p>

        <div
            class="field"
            style="text-align:right"
        >

            <label>
                توکن ربات
            </label>

            <input
                id="loginToken"
                class="input"
                type="password"
                placeholder="توکن ربات را وارد کنید"
            >

        </div>

        <button
            class="btn full"
            onclick="connect()"
        >
            ثبت و ورود به پنل ←
        </button>

        <div
            id="loginAlert"
            class="alert"
        >
            توکن شما در مرورگر ذخیره دائمی نمی‌شود.
        </div>

    </div>

</div>


<!-- =====================================================
APP
===================================================== -->

<div id="app" class="hidden">


<header class="topbar">

    <div class="top-actions">

        <button
            class="menuBtn"
            onclick="toggleSide()"
        >
            ☰
        </button>

        <div class="brand">

            <div class="brandIcon">
                🤖
            </div>

            پتی

        </div>

    </div>


    <div class="top-actions">

        <span class="pill">

            <span
                id="onlineDot"
                class="dot"
            ></span>

            ربات روشن

        </span>

        <span
            id="botNameTop"
            class="pill"
        >
            ربات من
        </span>

    </div>

</header>


<div class="layout">


<!-- =====================================================
SIDEBAR
===================================================== -->

<aside
    id="sidebar"
    class="sidebar"
>

    <div class="nav-title">
        مدیریت
    </div>

    <button
        class="nav active"
        onclick="showView('home',this)"
    >

        <b>⌂</b>

        داشبورد

    </button>


    <button
        class="nav"
        onclick="showView('users',this)"
    >

        <b>♙</b>

        کاربران

    </button>


    <button
        class="nav"
        onclick="showView('bots',this)"
    >

        <b>🤖</b>

        ربات‌ها

    </button>


    <button
        class="nav"
        onclick="showView('groups',this)"
    >

        <b>👥</b>

        گروه‌ها

    </button>


    <div class="nav-title">
        ساخت ربات
    </div>


    <button
        class="nav"
        onclick="showView('start',this)"
    >

        <b>🚀</b>

        متن شروع

    </button>


    <button
        class="nav"
        onclick="showView('commands',this)"
    >

        <b>⌘</b>

        دستورات

    </button>


    <button
        class="nav"
        onclick="showView('buttons',this)"
    >

        <b>⌨</b>

        دکمه‌ها

    </button>


    <button
        class="nav"
        onclick="showView('quick',this)"
    >

        <b>⚡</b>

        پاسخ سریع

    </button>


    <button
        class="nav"
        onclick="showView('console',this)"
    >

        <b>›_</b>

        کنسول

    </button>


    <div class="nav-title">
        سایر
    </div>


    <button
        class="nav"
        onclick="showView('settings',this)"
    >

        <b>⚙</b>

        تنظیمات

    </button>


    <button
        class="nav"
        onclick="logout()"
    >

        <b>↪</b>

        خروج

    </button>

</aside>


<!-- =====================================================
MAIN
===================================================== -->

<main class="main">


<!-- =====================================================
HOME
===================================================== -->

<section
    id="home"
    class="view active"
>

    <div class="hero">

        <h1>

            ساخت و مدیریت ربات

            <span>
                پتی
            </span>

        </h1>

        <p>
            یک پنل حرفه‌ای برای ساخت،
            مدیریت و کنترل ربات روبیکا؛
            با رابط ساده، سریع و کاملاً فارسی.
        </p>

    </div>


    <div class="grid4">


        <div class="stat">

            <div class="ico">
                👤
            </div>

            <div
                id="statUsers"
                class="num"
            >
                0
            </div>

            <div class="label">
                کاربران شناسایی‌شده
            </div>

        </div>


        <div class="stat">

            <div class="ico">
                💬
            </div>

            <div
                id="statChats"
                class="num"
            >
                0
            </div>

            <div class="label">
                چت‌های فعال
            </div>

        </div>


        <div class="stat">

            <div class="ico">
                ⚡
            </div>

            <div
                id="statMessages"
                class="num"
            >
                0
            </div>

            <div class="label">
                پیام‌های دریافت‌شده
            </div>

        </div>


        <div class="stat">

            <div class="ico">
                🟢
            </div>

            <div class="num">
                روشن
            </div>

            <div class="label">
                وضعیت ربات
            </div>

        </div>


    </div>


    <div class="section-title">

        <h2>
            امکانات پتی
        </h2>

        <span>
            مدیریت سریع
        </span>

    </div>


    <div class="grid3">


        <div
            class="card feature"
            onclick="showView('start')"
        >

            <div class="bigicon">
                🚀
            </div>

            <h3>
                متن شروع ربات
            </h3>

            <p>
                تنظیم پیام خوش‌آمدگویی و /start
            </p>

        </div>


        <div
            class="card feature"
            onclick="showView('console')"
        >

            <div class="bigicon">
                ›_
            </div>

            <h3>
                کنسول
            </h3>

            <p>
                نمایش لاگ‌ها و وضعیت ارتباط ربات
            </p>

        </div>


        <div
            class="card feature"
            onclick="showView('buttons')"
        >

            <div class="bigicon">
                ⌨
            </div>

            <h3>
                دکمه کیبورد
            </h3>

            <p>
                مدیریت دکمه‌های تعاملی کیبوردی
            </p>

        </div>


        <div
            class="card feature"
            onclick="showView('commands')"
        >

            <div class="bigicon">
                ⌘
            </div>

            <h3>
                دستورات
            </h3>

            <p>
                مدیریت دستورهای سفارشی ربات
            </p>

        </div>


        <div
            class="card feature"
            onclick="showView('quick')"
        >

            <div class="bigicon">
                ⚡
            </div>

            <h3>
                پاسخ سریع
            </h3>

            <p>
                پاسخ‌های آماده برای پیام‌های پرتکرار
            </p>

        </div>


        <div
            class="card feature"
            onclick="showView('users')"
        >

            <div class="bigicon">
                👥
            </div>

            <h3>
                مدیریت کاربران
            </h3>

            <p>
                کاربرانی که به ربات پیام داده‌اند
            </p>

        </div>


    </div>

</section>


<!-- =====================================================
USERS
===================================================== -->

<section
    id="users"
    class="view"
>

    <div class="section-title">

        <h2>
            مدیریت کاربران و چت‌ها
        </h2>

        <span>
            تشخیص خودکار chat_id
        </span>

    </div>


    <div class="card">

        <div class="toolbar">

            <button
                class="btn"
                onclick="loadChats()"
            >
                🔄 بروزرسانی
            </button>

            <span class="pill">
                هر پیام جدید خودکار ثبت می‌شود
            </span>

        </div>


        <div
            id="chatList"
            class="chatlist"
            style="margin-top:15px"
        >
        </div>

    </div>


    <div
        id="sendCard"
        class="card"
        style="margin-top:15px"
    >

        <h3>
            ✉️ ارسال پیام به چت انتخاب‌شده
        </h3>

        <div
            id="selectedInfo"
            class="alert"
        >
            یک چت را انتخاب کنید.
        </div>

        <textarea
            id="sendText"
            class="textarea"
            placeholder="متن پیام..."
        >سلام از پتی 👋</textarea>

        <br><br>

        <button
            class="btn"
            onclick="sendSelected()"
        >
            ارسال پیام
        </button>

        <div
            id="sendAlert"
            class="alert"
        >
        </div>

    </div>

</section>


<!-- =====================================================
BOTS
===================================================== -->

<section
    id="bots"
    class="view"
>

    <div class="section-title">

        <h2>
            مدیریت ربات
        </h2>

    </div>


    <div class="card">

        <div id="botDetails">
            در حال دریافت اطلاعات...
        </div>

        <div class="alert ok">

            ● اتصال فعال

            <br>

            دریافت پیام‌ها از طریق getUpdates

        </div>

    </div>

</section>


<!-- =====================================================
GROUPS
===================================================== -->

<section
    id="groups"
    class="view"
>

    <div class="section-title">

        <h2>
            گروه‌ها
        </h2>

        <span>
            نمایش چت‌های شناسایی‌شده
        </span>

    </div>


    <div class="card">

        <p
            style="
                color:#8198b5;
                line-height:2
            "
        >

            چت‌های گروهی که به ربات پیام
            بدهند از همان مسیر شناسایی
            می‌شوند.

            برای هر چت می‌توانی از بخش
            کاربران پیام ارسال کنی.

        </p>

    </div>

</section>


<!-- =====================================================
START
===================================================== -->

<section
    id="start"
    class="view"
>

    <div class="section-title">

        <h2>
            متن شروع ربات
        </h2>

        <span>
            تنظیم پیام خوش‌آمدگویی /start
        </span>

    </div>


    <div class="card">

        <div class="field">

            <label>
                متن پیام شروع
            </label>

            <textarea
                id="startText"
                class="textarea"
            >سلام 👋 به ربات پتی خوش آمدید.</textarea>

        </div>


        <button
            class="btn"
            onclick="saveStart()"
        >
            ذخیره متن شروع
        </button>


        <div
            id="startAlert"
            class="alert"
        >
            تغییرات را ذخیره کنید.
        </div>

    </div>

</section>


<!-- =====================================================
COMMANDS
===================================================== -->

<section
    id="commands"
    class="view"
>

    <div class="section-title">

        <h2>
            دستورات سفارشی
        </h2>

        <span>
            طراحی و مدیریت دستورها
        </span>

    </div>


    <div class="card">

        <div class="field">

            <label>
                نام دستور
            </label>

            <input
                id="cmdName"
                class="input"
                placeholder="/about"
            >

        </div>


        <div class="field">

            <label>
                پاسخ دستور
            </label>

            <textarea
                id="cmdReply"
                class="textarea"
                placeholder="متن پاسخ..."
            ></textarea>

        </div>


        <button
            class="btn"
            onclick="addCommand()"
        >
            + افزودن دستور
        </button>


        <div
            id="commandsList"
            style="margin-top:15px"
        >
        </div>

    </div>

</section>


<!-- =====================================================
BUTTONS
===================================================== -->

<section
    id="buttons"
    class="view"
>

    <div class="section-title">

        <h2>
            دکمه‌های کیبورد
        </h2>

        <span>
            مدیریت دکمه‌های تعاملی
        </span>

    </div>


    <div class="card">

        <div class="field">

            <label>
                عنوان دکمه
            </label>

            <input
                id="btnName"
                class="input"
                placeholder="درباره پتی"
            >

        </div>


        <div class="field">

            <label>
                متن پاسخ
            </label>

            <input
                id="btnReply"
                class="input"
                placeholder="پتی یک ربات‌ساز روبیکاست."
            >

        </div>


        <button
            class="btn"
            onclick="addButton()"
        >
            + افزودن دکمه
        </button>


        <div
            id="buttonsList"
            style="margin-top:15px"
        >
        </div>

    </div>

</section>


<!-- =====================================================
QUICK
===================================================== -->

<section
    id="quick"
    class="view"
>

    <div class="section-title">

        <h2>
            پاسخ سریع
        </h2>

        <span>
            پاسخ آماده به کلمات
        </span>

    </div>


    <div class="card">

        <div class="field">

            <label>
                کلمه یا عبارت
            </label>

            <input
                id="quickKey"
                class="input"
                placeholder="سلام"
            >

        </div>


        <div class="field">

            <label>
                پاسخ
            </label>

            <textarea
                id="quickReply"
                class="textarea"
                placeholder="سلام! خوش آمدید 👋"
            ></textarea>

        </div>


        <button
            class="btn"
            onclick="addQuick()"
        >
            + افزودن پاسخ سریع
        </button>


        <div
            id="quickList"
            style="margin-top:15px"
        >
        </div>

    </div>

</section>


<!-- =====================================================
CONSOLE
===================================================== -->

<section
    id="console"
    class="view"
>

    <div class="section-title">

        <h2>
            کنسول
        </h2>

        <span>
            نمایش لاگ‌ها و وضعیت
        </span>

    </div>


    <div class="card">

        <div
            id="consoleBox"
            class="console"
        >
[Peti] waiting for connection...
        </div>

    </div>

</section>


<!-- =====================================================
SETTINGS
===================================================== -->

<section
    id="settings"
    class="view"
>

    <div class="section-title">

        <h2>
            تنظیمات
        </h2>

    </div>


    <div class="card">

        <label class="switch">

            <input
                id="botSwitch"
                type="checkbox"
                checked
                onchange="toggleBot(this)"
            >

            <span class="slider"></span>

            <span>
                ربات روشن
            </span>

        </label>


        <div class="alert">

            این کلید وضعیت رابط کاربری را
            کنترل می‌کند.

            Worker دریافت پیام در پس‌زمینه
            فعال می‌ماند.

        </div>


        <button
            class="btn danger"
            onclick="logout()"
        >
            خروج از پنل
        </button>

    </div>

</section>


</main>

</div>

</div>


<script>

/* =====================================================
GLOBAL
===================================================== */

let token = "";

let selectedChat = "";

let bot = null;

let poll = null;

let commands =
    JSON.parse(
        localStorage.getItem(
            "peti_commands"
        ) || "[]"
    );

let buttons =
    JSON.parse(
        localStorage.getItem(
            "peti_buttons"
        ) || "[]"
    );

let quicks =
    JSON.parse(
        localStorage.getItem(
            "peti_quicks"
        ) || "[]"
    );


function $(id){

    return document.getElementById(id);

}


function esc(value){

    return String(
        value ?? ""
    )
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");

}


/* =====================================================
CONNECT
===================================================== */

async function connect(){

    const t =
        $("loginToken")
        .value
        .trim();

    if(!t){

        $("loginAlert").className =
            "alert err";

        $("loginAlert").innerText =
            "توکن را وارد کنید.";

        return;

    }

    $("loginAlert").className =
        "alert";

    $("loginAlert").innerText =
        "در حال اتصال...";


    try{

        const response =
            await fetch(
                "/api/connect",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            token:t
                        })
                }
            );


        const result =
            await response.json();


        if(!result.ok){

            $("loginAlert").className =
                "alert err";

            $("loginAlert").innerText =
                result.message ||
                "اتصال ناموفق بود.";

            return;

        }


        token = t;

        bot =
            result.bot || {};


        sessionStorage.setItem(
            "peti_token",
            token
        );


        $("login")
            .classList
            .add("hidden");


        $("app")
            .classList
            .remove("hidden");


        $("botNameTop").innerText =
            bot.name ||
            bot.first_name ||
            "ربات من";


        $("botDetails").innerHTML = `

            <p>
                نام:
                <b>
                    ${esc(
                        bot.name ||
                        bot.first_name ||
                        "نامشخص"
                    )}
                </b>
            </p>

            <p>
                username:
                <b>
                    ${esc(
                        bot.username ||
                        bot.user_name ||
                        "نامشخص"
                    )}
                </b>
            </p>

        `;


        log(
            "connected successfully"
        );


        loadSettings();

        loadChats();

        startPoll();


    }catch(error){

        $("loginAlert").className =
            "alert err";

        $("loginAlert").innerText =
            "خطا در ارتباط با سرور.";

    }

}


/* =====================================================
LOGOUT
===================================================== */

function logout(){

    sessionStorage.removeItem(
        "peti_token"
    );

    location.reload();

}


/* =====================================================
SIDEBAR
===================================================== */

function toggleSide(){

    $("sidebar")
        .classList
        .toggle("open");

}


/* =====================================================
VIEW
===================================================== */

function showView(
    id,
    element
){

    document
        .querySelectorAll(".view")
        .forEach(
            x =>
                x.classList.remove(
                    "active"
                )
        );


    $(id)
        .classList
        .add("active");


    document
        .querySelectorAll(".nav")
        .forEach(
            x =>
                x.classList.remove(
                    "active"
                )
        );


    if(element){

        element
            .classList
            .add("active");

    }


    if(id === "users"){

        loadChats();

    }


    if(
        window.innerWidth < 900
    ){

        $("sidebar")
            .classList
            .remove("open");

    }

}


/* =====================================================
POLL
===================================================== */

function startPoll(){

    if(poll){

        clearInterval(
            poll
        );

    }

    poll =
        setInterval(
            loadChats,
            2500
        );

}


/* =====================================================
LOAD CHATS
===================================================== */

async function loadChats(){

    if(!token){

        return;

    }


    try{

        const response =
            await fetch(
                "/api/chats?token=" +
                encodeURIComponent(token)
            );


        const result =
            await response.json();


        if(result.ok){

            renderChats(
                result.chats || []
            );

        }

    }catch(error){

        console.log(error);

    }

}


/* =====================================================
RENDER CHATS
===================================================== */

function renderChats(
    list
){

    $("statUsers").innerText =
        list.length;


    $("statChats").innerText =
        list.length;


    $("statMessages").innerText =
        list.reduce(
            (
                total,
                item
            ) =>
                total +
                Number(
                    item.messages || 0
                ),
            0
        );


    const box =
        $("chatList");


    if(!list.length){

        box.innerHTML = `

            <div class="alert">

                هنوز هیچ کاربری به ربات
                پیام نداده است.

                <br><br>

                یک پیام مثل

                <b>
                    /start
                </b>

                بفرستید.

            </div>

        `;

        return;

    }


    box.innerHTML =
        list.map(
            chat => `

        <div
            class="
                chat
                ${
                    String(chat.chat_id)
                    ===
                    String(selectedChat)
                    ?
                    "sel"
                    :
                    ""
                }
            "
            onclick="
                selectChat(
                    '${esc(chat.chat_id)}',
                    '${esc(chat.name || "کاربر")}'
                )
            "
        >

            <div class="chat-main">

                <div class="chat-name">

                    👤

                    ${esc(
                        chat.name ||
                        "کاربر"
                    )}

                    ${
                        chat.username
                        ?
                        `<span>
                            @${esc(chat.username)}
                        </span>`
                        :
                        ""
                    }

                </div>


                <div class="chat-id">

                    ${esc(
                        chat.chat_id
                    )}

                </div>


                <div class="chat-last">

                    ${esc(
                        chat.last_text ||
                        "بدون متن"
                    )}

                </div>

            </div>


            <span class="badge">

                ${
                    Number(
                        chat.messages || 0
                    )
                }

                پیام

            </span>

        </div>

    `
        )
        .join("");

}


/* =====================================================
SELECT CHAT
===================================================== */

function selectChat(
    id,
    name
){

    selectedChat = id;


    $("selectedInfo").innerHTML = `

        چت انتخاب‌شده:

        <b>
            ${esc(name)}
        </b>

        <br>

        <span
            style="
                direction:ltr;
                display:inline-block
            "
        >
            ${esc(id)}
        </span>

    `;


    log(
        "selected chat: " +
        id
    );


    showView(
        "users"
    );


    loadChats();

}


/* =====================================================
SEND MESSAGE
===================================================== */

async function sendSelected(){

    if(!selectedChat){

        $("sendAlert").className =
            "alert err";

        $("sendAlert").innerText =
            "یک چت را انتخاب کنید.";

        return;

    }


    const text =
        $("sendText")
        .value
        .trim();


    if(!text){

        $("sendAlert").className =
            "alert err";

        $("sendAlert").innerText =
            "متن پیام خالی است.";

        return;

    }


    $("sendAlert").className =
        "alert";

    $("sendAlert").innerText =
        "در حال ارسال...";


    try{

        const response =
            await fetch(
                "/api/send",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            token:token,

                            chat_id:
                                selectedChat,

                            text:text

                        })

                }
            );


        const result =
            await response.json();


        if(result.ok){

            $("sendAlert").className =
                "alert ok";

            $("sendAlert").innerText =
                "پیام با موفقیت ارسال شد.";

            log(
                "message sent to " +
                selectedChat
            );

            loadChats();

        }else{

            $("sendAlert").className =
                "alert err";

            $("sendAlert").innerText =
                result.message ||
                "ارسال ناموفق بود.";

        }


    }catch(error){

        $("sendAlert").className =
            "alert err";

        $("sendAlert").innerText =
            "خطا در ارسال پیام.";

    }

}


/* =====================================================
START MESSAGE
===================================================== */

async function saveStart(){

    const text =
        $("startText")
        .value
        .trim();


    const response =
        await fetch(
            "/api/start-message",
            {
                method:"POST",

                headers:{
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({
                        token:token,
                        text:text
                    })
            }
        );


    const result =
        await response.json();


    $("startAlert").className =
        result.ok
        ?
        "alert ok"
        :
        "alert err";


    $("startAlert").innerText =
        result.ok
        ?
        "متن شروع ذخیره شد."
        :
        "ذخیره ناموفق بود.";

}


/* =====================================================
SETTINGS
===================================================== */

async function loadSettings(){

    try{

        const response =
            await fetch(
                "/api/settings"
            );


        const result =
            await response.json();


        $("startText").value =
            result.start_message ||
            "";

    }catch(error){

        console.log(error);

    }

}


/* =====================================================
COMMANDS
===================================================== */

function addCommand(){

    const name =
        $("cmdName")
        .value
        .trim();


    const reply =
        $("cmdReply")
        .value
        .trim();


    if(!name || !reply){

        return;

    }


    commands.push({
        n:name,
        r:reply
    });


    localStorage.setItem(
        "peti_commands",
        JSON.stringify(
            commands
        )
    );


    $("cmdName").value = "";

    $("cmdReply").value = "";


    renderLocal(
        "commandsList",
        commands
    );

}


/* =====================================================
BUTTONS
===================================================== */

function addButton(){

    const name =
        $("btnName")
        .value
        .trim();


    const reply =
        $("btnReply")
        .value
        .trim();


    if(!name || !reply){

        return;

    }


    buttons.push({
        n:name,
        r:reply
    });


    localStorage.setItem(
        "peti_buttons",
        JSON.stringify(
            buttons
        )
    );


    $("btnName").value = "";

    $("btnReply").value = "";


    renderLocal(
        "buttonsList",
        buttons
    );

}


/* =====================================================
QUICK REPLIES
===================================================== */

function addQuick(){

    const name =
        $("quickKey")
        .value
        .trim();


    const reply =
        $("quickReply")
        .value
        .trim();


    if(!name || !reply){

        return;

    }


    quicks.push({
        n:name,
        r:reply
    });


    localStorage.setItem(
        "peti_quicks",
        JSON.stringify(
            quicks
        )
    );


    $("quickKey").value = "";

    $("quickReply").value = "";


    renderLocal(
        "quickList",
        quicks
    );

}


/* =====================================================
LOCAL LIST
===================================================== */

function renderLocal(
    id,
    list
){

    $(id).innerHTML =
        list.map(
            (
                item,
                index
            ) => `

        <div
            class="chat"
            style="margin-bottom:8px"
        >

            <div>

                <b>
                    ${esc(item.n)}
                </b>

                <div class="chat-last">

                    ${esc(item.r)}

                </div>

            </div>


            <button
                class="btn danger"
                onclick="
                    removeLocal(
                        '${id}',
                        ${index}
                    )
                "
            >
                حذف
            </button>

        </div>

    `
        )
        .join("");

}


/* =====================================================
REMOVE LOCAL
===================================================== */

function removeLocal(
    id,
    index
){

    if(
        id ===
        "commandsList"
    ){

        commands.splice(
            index,
            1
        );

        localStorage.setItem(
            "peti_commands",
            JSON.stringify(
                commands
            )
        );

        renderLocal(
            id,
            commands
        );

    }


    if(
        id ===
        "buttonsList"
    ){

        buttons.splice(
            index,
            1
        );

        localStorage.setItem(
            "peti_buttons",
            JSON.stringify(
                buttons
            )
        );

        renderLocal(
            id,
            buttons
        );

    }


    if(
        id ===
        "quickList"
    ){

        quicks.splice(
            index,
            1
        );

        localStorage.setItem(
            "peti_quicks",
            JSON.stringify(
                quicks
            )
        );

        renderLocal(
            id,
            quicks
        );

    }

}


/* =====================================================
CONSOLE
===================================================== */

function log(
    text
){

    const box =
        $("consoleBox");


    if(!box){

        return;

    }


    box.innerText +=

        "[" +
        new Date()
            .toLocaleTimeString(
                "fa-IR"
            ) +
        "] " +
        text +
        "\n";


    box.scrollTop =
        box.scrollHeight;

}


/* =====================================================
BOT SWITCH
===================================================== */

function toggleBot(
    element
){

    if(
        element.checked
    ){

        $("onlineDot")
            .style
            .background =
            "#31e6a0";

        log(
            "bot status: ON"
        );

    }else{

        $("onlineDot")
            .style
            .background =
            "#ff6685";

        log(
            "bot status: OFF"
        );

    }

}


/* =====================================================
PAGE LOAD
===================================================== */

window.addEventListener(
    "load",
    () => {

        renderLocal(
            "commandsList",
            commands
        );

        renderLocal(
            "buttonsList",
            buttons
        );

        renderLocal(
            "quickList",
            quicks
        );


        const savedToken =
            sessionStorage.getItem(
                "peti_token"
            );


        if(savedToken){

            $("loginToken").value =
                savedToken;

            connect();

        }

    }
);

</script>


</body>

</html>
"""


# =========================================================
# HOME
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    return HTML


# =========================================================
# RUN
# =========================================================

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
