import os
import time
import threading
from typing import Optional

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# =========================================================
# PETI RUBIKA BOT BUILDER
# Single-file Render version
# =========================================================

app = FastAPI(title="Peti Rubika Bot Builder")

API_BASE = "https://botapi.rubika.ir/v3"

# ---------------------------------------------------------
# حافظه موقت برنامه
# توجه: روی Render Free با Restart/Spin-down پاک می‌شود.
# ---------------------------------------------------------

bots = {}
lock = threading.Lock()


# =========================================================
# RUBIKA API
# =========================================================

def rubika_request(
    token: str,
    method: str,
    data: Optional[dict] = None
):
    token = token.strip()

    if not token:
        raise Exception("توکن خالی است.")

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
        result = response.json()
    except Exception:
        raise Exception(
            f"پاسخ نامعتبر از روبیکا دریافت شد. "
            f"HTTP {response.status_code}"
        )

    if response.status_code >= 400:
        raise Exception(
            f"HTTP {response.status_code}: {result}"
        )

    return result


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
        "limit": 20
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
# استخراج اطلاعات Update
# =========================================================

def extract_chat_id(update):
    if not isinstance(update, dict):
        return None

    # حالت اصلی
    value = update.get("chat_id")

    if value:
        return str(value)

    # حالت‌های احتمالی
    for key in [
        "chatId",
        "object_guid",
        "objectGuid"
    ]:
        value = update.get(key)

        if value:
            return str(value)

    # داخل پیام
    for message_key in [
        "new_message",
        "message",
        "updated_message"
    ]:
        message = update.get(message_key)

        if not isinstance(message, dict):
            continue

        for key in [
            "chat_id",
            "chatId",
            "object_guid",
            "objectGuid"
        ]:
            value = message.get(key)

            if value:
                return str(value)

    return None


def extract_text(update):
    if not isinstance(update, dict):
        return ""

    for key in [
        "new_message",
        "message",
        "updated_message"
    ]:
        message = update.get(key)

        if isinstance(message, dict):

            text = message.get("text")

            if text is not None:
                return str(text)

    text = update.get("text")

    if text is not None:
        return str(text)

    return ""


def extract_sender_name(update):
    if not isinstance(update, dict):
        return ""

    candidates = [
        update.get("sender"),
        update.get("user"),
        update.get("from")
    ]

    for obj in candidates:

        if isinstance(obj, dict):

            for key in [
                "first_name",
                "name",
                "username",
                "user_name"
            ]:
                value = obj.get(key)

                if value:
                    return str(value)

    for message_key in [
        "new_message",
        "message"
    ]:
        message = update.get(message_key)

        if isinstance(message, dict):

            for key in [
                "first_name",
                "name",
                "username",
                "user_name"
            ]:
                value = message.get(key)

                if value:
                    return str(value)

    return ""


# =========================================================
# Bot Worker
# =========================================================

def bot_worker(token):

    print("======================================")
    print("Peti Bot Worker Started")
    print("======================================")

    offset_id = None

    while True:

        try:

            result = get_updates(
                token,
                offset_id
            )

            if not isinstance(result, dict):
                time.sleep(2)
                continue

            # ---------------------------------------------
            # استخراج data
            # ---------------------------------------------

            data = result.get("data")

            if not isinstance(data, dict):
                data = result

            updates = data.get("updates")

            if not isinstance(updates, list):
                updates = []

            # ---------------------------------------------
            # offset بعدی
            # ---------------------------------------------

            next_offset = (
                data.get("next_offset_id")
                or result.get("next_offset_id")
            )

            if next_offset:
                offset_id = str(next_offset)

            # ---------------------------------------------
            # پردازش پیام‌ها
            # ---------------------------------------------

            for update in updates:

                if not isinstance(update, dict):
                    continue

                chat_id = extract_chat_id(update)

                if not chat_id:
                    print(
                        "Update received but chat_id "
                        "was not found."
                    )
                    continue

                text = extract_text(update)

                sender_name = extract_sender_name(update)

                now = int(time.time())

                # -----------------------------------------
                # ذخیره چت
                # -----------------------------------------

                with lock:

                    bot = bots.get(token)

                    if bot is None:
                        continue

                    chats = bot["chats"]

                    existing = chats.get(chat_id)

                    if existing is None:

                        chats[chat_id] = {
                            "chat_id": chat_id,
                            "name": (
                                sender_name
                                or "کاربر جدید"
                            ),
                            "last_text": text,
                            "last_update": update,
                            "updated_at": now,
                            "messages": 1
                        }

                        print(
                            f"NEW CHAT FOUND: {chat_id}"
                        )

                    else:

                        existing["last_text"] = text
                        existing["last_update"] = update
                        existing["updated_at"] = now
                        existing["messages"] += 1

                        if sender_name:
                            existing["name"] = sender_name

                # -----------------------------------------
                # پاسخ خودکار
                # -----------------------------------------

                if text.strip() == "/start":

                    try:

                        send_message(
                            token,
                            chat_id,
                            "سلام 👋\n\n"
                            "به ربات پتی خوش آمدید.\n"
                            "چت شما با موفقیت شناسایی شد."
                        )

                    except Exception as e:

                        print(
                            "Auto reply error:",
                            e
                        )

                elif text.strip() == "/help":

                    try:

                        send_message(
                            token,
                            chat_id,
                            "🤖 راهنمای ربات پتی\n\n"
                            "/start - شروع ربات\n"
                            "/help - راهنما"
                        )

                    except Exception as e:

                        print(
                            "Help reply error:",
                            e
                        )

            time.sleep(1)

        except Exception as e:

            print(
                "Worker error:",
                repr(e)
            )

            time.sleep(5)


# =========================================================
# Models
# =========================================================

class TokenRequest(BaseModel):
    token: str


class SendMessageRequest(BaseModel):
    token: str
    chat_id: str
    text: str


# =========================================================
# Health
# =========================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "Peti Rubika Bot Builder"
    }


# =========================================================
# Verify Token
# =========================================================

@app.post("/api/verify-token")
def verify_token(req: TokenRequest):

    token = req.token.strip()

    if not token:

        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    try:

        result = get_me(token)

        bot_data = result.get(
            "data",
            result
        )

        # ---------------------------------------------
        # ایجاد حافظه ربات
        # ---------------------------------------------

        with lock:

            if token not in bots:

                bots[token] = {
                    "bot": bot_data,
                    "chats": {},
                    "worker_started": False
                }

            else:

                bots[token]["bot"] = bot_data

            # -----------------------------------------
            # شروع Worker
            # -----------------------------------------

            if not bots[token]["worker_started"]:

                bots[token]["worker_started"] = True

                thread = threading.Thread(
                    target=bot_worker,
                    args=(token,),
                    daemon=True
                )

                thread.start()

        return {
            "ok": True,
            "message": "ربات با موفقیت متصل شد.",
            "bot": bot_data
        }

    except Exception as e:

        print(
            "Verify token error:",
            repr(e)
        )

        return {
            "ok": False,
            "message": str(e)
        }


# =========================================================
# گرفتن لیست چت‌ها
# =========================================================

@app.get("/api/chats")
def get_chats(token: str):

    token = token.strip()

    if not token:

        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    with lock:

        bot = bots.get(token)

        if not bot:

            return {
                "ok": False,
                "message": "ربات هنوز متصل نشده است.",
                "chats": []
            }

        chats = list(
            bot["chats"].values()
        )

    # جدیدترین‌ها اول
    chats.sort(
        key=lambda x: x.get(
            "updated_at",
            0
        ),
        reverse=True
    )

    return {
        "ok": True,
        "chats": chats
    }


# =========================================================
# ارسال پیام به چت انتخاب شده
# =========================================================

@app.post("/api/send-message")
def api_send_message(
    req: SendMessageRequest
):

    token = req.token.strip()
    chat_id = req.chat_id.strip()
    text = req.text.strip()

    if not token:
        return {
            "ok": False,
            "message": "توکن خالی است."
        }

    if not chat_id:
        return {
            "ok": False,
            "message": "چتی انتخاب نشده است."
        }

    if not text:
        return {
            "ok": False,
            "message": "متن پیام خالی است."
        }

    try:

        result = send_message(
            token,
            chat_id,
            text
        )

        return {
            "ok": True,
            "message": "پیام ارسال شد.",
            "result": result
        }

    except Exception as e:

        print(
            "Send message error:",
            repr(e)
        )

        return {
            "ok": False,
            "message": str(e)
        }


# =========================================================
# HTML
# =========================================================

HTML = r"""
<!DOCTYPE html>

<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>پتی ربات‌ساز روبیکا</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    min-height:100vh;

    font-family:
        Tahoma,
        Arial,
        sans-serif;

    color:#fff;

    background:
        radial-gradient(
            circle at top,
            #12304d,
            #07111d 50%,
            #03070d
        );
}

.container{
    width:min(1050px,94%);
    margin:35px auto;
}

.header{
    text-align:center;
    margin-bottom:25px;
}

.logo{
    width:72px;
    height:72px;

    margin:auto;

    display:flex;
    align-items:center;
    justify-content:center;

    border-radius:22px;

    font-size:34px;
    font-weight:bold;

    color:#00121d;

    background:
        linear-gradient(
            135deg,
            #00e5ff,
            #087cff
        );

    box-shadow:
        0 0 35px
        rgba(0,220,255,.35);
}

h1{
    margin:15px 0 5px;
}

.subtitle{
    color:#8da5b9;
}

.card{
    background:
        rgba(7,22,36,.9);

    border:
        1px solid
        rgba(0,220,255,.13);

    border-radius:22px;

    padding:22px;

    margin-bottom:18px;

    box-shadow:
        0 20px 60px
        rgba(0,0,0,.25);
}

.card h2{
    margin-top:0;
}

label{
    display:block;

    color:#9bb1c4;

    margin:
        12px 0 7px;
}

input,
textarea{

    width:100%;

    background:#06121e;

    border:
        1px solid
        #20394c;

    border-radius:13px;

    padding:13px;

    color:#fff;

    outline:none;

    font-size:15px;
}

input:focus,
textarea:focus{
    border-color:#00dcff;
}

textarea{
    min-height:100px;
    resize:vertical;
}

button{

    border:0;

    border-radius:13px;

    padding:
        12px 18px;

    margin-top:13px;

    font-weight:bold;

    cursor:pointer;

    background:
        linear-gradient(
            135deg,
            #00d9ff,
            #087cff
        );

    color:#00131d;
}

button.secondary{
    background:#14293a;
    color:#d7f8ff;
}

button.danger{
    background:#301923;
    color:#ffb5c3;
}

button:hover{
    transform:translateY(-1px);
}

.status{

    margin-top:14px;

    padding:13px;

    border-radius:13px;

    background:#081724;

    color:#91a8bb;
}

.success{
    color:#57efad;
}

.error{
    color:#ff7272;
}

.layout{

    display:grid;

    grid-template-columns:
        330px 1fr;

    gap:18px;
}

.chats{
    display:flex;

    flex-direction:column;

    gap:9px;

    max-height:500px;

    overflow-y:auto;
}

.chat{

    padding:13px;

    border-radius:14px;

    background:#091a2a;

    border:
        1px solid
        #1a3347;

    cursor:pointer;
}

.chat:hover{
    border-color:#00cfee;
}

.chat.active{
    border-color:#00dcff;

    background:#0b2537;
}

.chat-name{
    font-weight:bold;
}

.chat-id{
    color:#698399;

    font-size:11px;

    direction:ltr;

    text-align:right;

    margin-top:5px;
}

.chat-last{
    color:#8ca5b8;

    font-size:12px;

    margin-top:7px;

    white-space:nowrap;

    overflow:hidden;

    text-overflow:ellipsis;
}

.empty{
    text-align:center;

    padding:25px;

    color:#687f92;
}

.selected{

    padding:12px;

    border-radius:12px;

    background:#071925;

    color:#9eb4c6;
}

.selected strong{
    color:#4ce9ff;
}

.top-actions{
    display:flex;

    gap:8px;

    flex-wrap:wrap;
}

.small{
    font-size:12px;
    color:#7891a5;
}

.footer{
    text-align:center;

    color:#5e7488;

    margin:30px 0;
}

@media(max-width:750px){

    .layout{
        grid-template-columns:1fr;
    }

}

</style>

</head>

<body>

<div class="container">


    <div class="header">

        <div class="logo">
            پ
        </div>

        <h1>
            پتی ربات‌ساز
        </h1>

        <div class="subtitle">
            مدیریت هوشمند ربات روبیکا
        </div>

    </div>


    <!-- اتصال -->

    <div class="card">

        <h2>
            🔐 اتصال ربات
        </h2>

        <label>
            توکن ربات
        </label>

        <input
            id="token"
            type="password"
            placeholder="توکن ربات روبیکا"
        >

        <div class="top-actions">

            <button onclick="connectBot()">
                اتصال ربات
            </button>

            <button
                class="secondary"
                onclick="refreshChats()"
            >
                🔄 بروزرسانی چت‌ها
            </button>

        </div>

        <div
            id="status"
            class="status"
        >
            ربات هنوز متصل نشده است.
        </div>

    </div>


    <!-- اطلاعات ربات -->

    <div
        id="botCard"
        class="card"
        style="display:none"
    >

        <h2>
            🤖 ربات
        </h2>

        <div id="botInfo"></div>

    </div>


    <!-- چت‌ها -->

    <div class="layout">


        <div class="card">

            <h2>
                💬 چت‌ها
            </h2>

            <div class="small">
                هر کاربری که به ربات پیام بدهد
                خودکار اینجا اضافه می‌شود.
            </div>

            <div
                id="chats"
                class="chats"
                style="margin-top:15px"
            >

                <div class="empty">
                    هنوز چتی پیدا نشده است.
                </div>

            </div>

        </div>


        <!-- ارسال -->

        <div class="card">

            <h2>
                ✉️ ارسال پیام
            </h2>

            <div
                id="selected"
                class="selected"
            >
                هیچ چتی انتخاب نشده است.
            </div>

            <label>
                متن پیام
            </label>

            <textarea
                id="message"
                placeholder="متن پیام را بنویسید..."
            >سلام از پتی 👋</textarea>

            <button onclick="sendMessage()">
                ارسال پیام
            </button>

            <div
                id="sendStatus"
                class="status"
            >
                یک چت را انتخاب کنید.
            </div>

        </div>


    </div>


    <div class="footer">
        پتی ربات‌ساز روبیکا
    </div>


</div>


<script>

let currentToken = "";

let selectedChatId = "";

let polling = null;


/* ========================================================
   اتصال
======================================================== */

async function connectBot(){

    const token =
        document
        .getElementById("token")
        .value
        .trim();

    const status =
        document
        .getElementById("status");

    if(!token){

        status.className =
            "status error";

        status.innerText =
            "توکن را وارد کنید.";

        return;
    }

    currentToken = token;

    status.className =
        "status";

    status.innerText =
        "در حال اتصال به روبیکا...";

    try{

        const response =
            await fetch(
                "/api/verify-token",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({
                        token:token
                    })
                }
            );

        const result =
            await response.json();

        if(!result.ok){

            status.className =
                "status error";

            status.innerText =
                result.message ||
                "اتصال ناموفق بود.";

            return;
        }

        status.className =
            "status success";

        status.innerText =
            "✅ ربات متصل شد. حالا کاربران می‌توانند به ربات پیام بدهند.";

        showBot(result.bot);

        refreshChats();

        startPolling();

    }catch(error){

        status.className =
            "status error";

        status.innerText =
            "خطا در ارتباط با سرور.";

        console.error(error);
    }
}


/* ========================================================
   اطلاعات ربات
======================================================== */

function showBot(bot){

    const card =
        document
        .getElementById("botCard");

    const info =
        document
        .getElementById("botInfo");

    card.style.display = "block";

    if(!bot){

        info.innerText =
            "ربات متصل شد.";

        return;
    }

    const name =
        bot.name ||
        bot.first_name ||
        "نامشخص";

    const username =
        bot.username ||
        bot.user_name ||
        "نامشخص";

    info.innerHTML = `
        <p>
            نام:
            <strong>
                ${escapeHtml(name)}
            </strong>
        </p>

        <p>
            username:
            <strong>
                ${escapeHtml(username)}
            </strong>
        </p>
    `;
}


/* ========================================================
   دریافت چت‌ها
======================================================== */

async function refreshChats(){

    if(!currentToken){

        return;
    }

    try{

        const response =
            await fetch(
                "/api/chats?token=" +
                encodeURIComponent(
                    currentToken
                )
            );

        const result =
            await response.json();

        if(!result.ok){

            console.log(
                result.message
            );

            return;
        }

        renderChats(
            result.chats || []
        );

    }catch(error){

        console.error(error);
    }
}


/* ========================================================
   نمایش چت‌ها
======================================================== */

function renderChats(chats){

    const box =
        document
        .getElementById("chats");

    if(!chats.length){

        box.innerHTML = `
            <div class="empty">
                هنوز هیچ کاربری به ربات پیام نداده است.
            </div>
        `;

        return;
    }

    box.innerHTML = "";

    chats.forEach(chat => {

        const item =
            document.createElement("div");

        item.className = "chat";

        if(
            String(chat.chat_id)
            ===
            String(selectedChatId)
        ){
            item.classList.add("active");
        }

        item.onclick = () => {

            selectChat(
                chat.chat_id,
                chat.name
            );

        };

        item.innerHTML = `

            <div class="chat-name">
                👤
                ${escapeHtml(
                    chat.name ||
                    "کاربر"
                )}
            </div>

            <div class="chat-id">
                ${escapeHtml(
                    chat.chat_id
                )}
            </div>

            <div class="chat-last">
                ${escapeHtml(
                    chat.last_text ||
                    "بدون متن"
                )}
            </div>

        `;

        box.appendChild(item);

    });
}


/* ========================================================
   انتخاب چت
======================================================== */

function selectChat(
    chatId,
    name
){

    selectedChatId =
        String(chatId);

    document
        .getElementById("selected")
        .innerHTML = `
            چت انتخاب شده:
            <strong>
                ${escapeHtml(
                    name ||
                    "کاربر"
                )}
            </strong>
            <br>
            <span
                style="
                direction:ltr;
                display:inline-block;
                margin-top:5px;
                "
            >
                ${escapeHtml(
                    selectedChatId
                )}
            </span>
        `;

    document
        .getElementById("sendStatus")
        .innerText =
            "آماده ارسال.";

    refreshChats();
}


/* ========================================================
   ارسال پیام
======================================================== */

async function sendMessage(){

    const text =
        document
        .getElementById("message")
        .value
        .trim();

    const status =
        document
        .getElementById("sendStatus");

    if(!currentToken){

        status.className =
            "status error";

        status.innerText =
            "ابتدا ربات را متصل کنید.";

        return;
    }

    if(!selectedChatId){

        status.className =
            "status error";

        status.innerText =
            "ابتدا یک چت را انتخاب کنید.";

        return;
    }

    if(!text){

        status.className =
            "status error";

        status.innerText =
            "متن پیام خالی است.";

        return;
    }

    status.className =
        "status";

    status.innerText =
        "در حال ارسال...";

    try{

        const response =
            await fetch(
                "/api/send-message",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        token:
                            currentToken,

                        chat_id:
                            selectedChatId,

                        text:
                            text

                    })
                }
            );

        const result =
            await response.json();

        if(result.ok){

            status.className =
                "status success";

            status.innerText =
                "✅ پیام با موفقیت ارسال شد.";

        }else{

            status.className =
                "status error";

            status.innerText =
                result.message ||
                "ارسال ناموفق بود.";
        }

    }catch(error){

        status.className =
            "status error";

        status.innerText =
            "خطا در ارتباط با سرور.";

        console.error(error);
    }
}


/* ========================================================
   Polling پنل
======================================================== */

function startPolling(){

    if(polling){

        clearInterval(
            polling
        );
    }

    polling =
        setInterval(
            refreshChats,
            2500
        );
}


/* ========================================================
   Escape HTML
======================================================== */

function escapeHtml(value){

    return String(value)

        .replaceAll(
            "&",
            "&amp;"
        )

        .replaceAll(
            "<",
            "&lt;"
        )

        .replaceAll(
            ">",
            "&gt;"
        )

        .replaceAll(
            '"',
            "&quot;"
        )

        .replaceAll(
            "'",
            "&#039;"
        );
}

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
