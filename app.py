from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import requests
import threading
import time
import json
from typing import Optional

app = FastAPI(title="Peti Rubika Bot Builder")

API_BASE = "https://botapi.rubika.ir/v3"

# توکن‌ها و وضعیت ربات‌ها
bots = {}
lock = threading.Lock()


# =========================
# Rubika API
# =========================

def rubika_request(token: str, method: str, data=None):
    token = token.strip()

    url = f"{API_BASE}/{token}/{method}"

    response = requests.post(
        url,
        json=data or {},
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    try:
        result = response.json()
    except Exception:
        raise Exception(
            f"پاسخ نامعتبر از روبیکا: HTTP {response.status_code}"
        )

    if response.status_code >= 400:
        raise Exception(
            f"HTTP {response.status_code}: {result}"
        )

    return result


def get_me(token):
    return rubika_request(token, "getMe", {})


def get_updates(token, offset_id=None):
    data = {
        "limit": 20
    }

    if offset_id:
        data["offset_id"] = offset_id

    return rubika_request(token, "getUpdates", data)


def send_message(token, chat_id, text):
    return rubika_request(
        token,
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": str(text)
        }
    )


# =========================
# استخراج chat_id
# =========================

def extract_chat_id(update):
    """
    ساختار اصلی روبیکا:
    {
        "type": "NewMessage",
        "chat_id": "...",
        "new_message": {...}
    }

    علاوه بر آن چند حالت جایگزین هم بررسی می‌شود.
    """

    if not isinstance(update, dict):
        return None

    # حالت اصلی
    chat_id = update.get("chat_id")

    if chat_id:
        return str(chat_id)

    # حالت‌های احتمالی دیگر
    for key in [
        "chatId",
        "object_guid",
        "objectGuid"
    ]:
        value = update.get(key)
        if value:
            return str(value)

    # بررسی داخل message
    for message_key in [
        "new_message",
        "updated_message",
        "message"
    ]:
        message = update.get(message_key)

        if isinstance(message, dict):
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
        "updated_message",
        "message"
    ]:
        message = update.get(key)

        if isinstance(message, dict):
            text = message.get("text")

            if text:
                return str(text)

    return str(update.get("text") or "")


# =========================
# دریافت خودکار پیام‌ها
# =========================

def bot_worker(token):
    offset_id = None

    print("Peti bot worker started.")

    while True:
        try:
            result = get_updates(token, offset_id)

            if not isinstance(result, dict):
                time.sleep(2)
                continue

            data = result.get("data")

            if not isinstance(data, dict):
                data = result

            updates = data.get("updates", [])

            if not isinstance(updates, list):
                updates = []

            # offset بعدی
            next_offset = (
                data.get("next_offset_id")
                or result.get("next_offset_id")
            )

            if next_offset:
                offset_id = str(next_offset)

            for update in updates:

                if not isinstance(update, dict):
                    continue

                chat_id = extract_chat_id(update)

                if not chat_id:
                    continue

                text = extract_text(update)

                # ذخیره chat_id
                with lock:
                    bot = bots.get(token)

                    if bot is not None:
                        bot["chat_id"] = chat_id
                        bot["last_text"] = text
                        bot["last_update"] = update
                        bot["updated_at"] = time.time()

                print(
                    f"[Peti] chat_id found: {chat_id} | text: {text}"
                )

                # پاسخ‌های ساده
                if text.strip() == "/start":
                    try:
                        send_message(
                            token,
                            chat_id,
                            "سلام 👋\n"
                            "ربات پتی با موفقیت به شما متصل شد.\n\n"
                            f"chat_id شما:\n{chat_id}"
                        )
                    except Exception as e:
                        print("Send message error:", e)

                elif text.strip() == "/help":
                    try:
                        send_message(
                            token,
                            chat_id,
                            "راهنمای ربات پتی\n\n"
                            "/start - شروع\n"
                            "/help - راهنما"
                        )
                    except Exception as e:
                        print("Send message error:", e)

            time.sleep(1)

        except Exception as e:
            print("Worker error:", e)
            time.sleep(5)


# =========================
# Models
# =========================

class TokenRequest(BaseModel):
    token: str


class SendMessageRequest(BaseModel):
    token: str
    chat_id: str
    text: str


# =========================
# API Routes
# =========================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Peti Rubika Bot Builder"
    }


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

        # ذخیره ربات
        with lock:
            if token not in bots:
                bots[token] = {
                    "chat_id": None,
                    "last_text": "",
                    "last_update": None,
                    "updated_at": 0,
                    "worker_started": False
                }

            # شروع Worker فقط یک بار
            if not bots[token]["worker_started"]:
                bots[token]["worker_started"] = True

                thread = threading.Thread(
                    target=bot_worker,
                    args=(token,),
                    daemon=True
                )

                thread.start()

        data = result.get("data", result)

        return {
            "ok": True,
            "message": "اتصال با موفقیت انجام شد.",
            "bot": data,
            "chat_id": bots[token].get("chat_id")
        }

    except Exception as e:

        print("Verify error:", e)

        return {
            "ok": False,
            "message": str(e)
        }


@app.get("/api/chat-id")
def get_chat_id(token: str):

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
                "message": "ابتدا توکن را متصل کنید."
            }

        chat_id = bot.get("chat_id")

    if chat_id:
        return {
            "ok": True,
            "chat_id": chat_id
        }

    return {
        "ok": False,
        "message": "هنوز chat_id پیدا نشده است. یک پیام به ربات بفرستید."
    }


@app.post("/api/send-message")
def api_send_message(req: SendMessageRequest):

    try:

        result = send_message(
            req.token.strip(),
            req.chat_id.strip(),
            req.text
        )

        return {
            "ok": True,
            "message": "پیام ارسال شد.",
            "result": result
        }

    except Exception as e:

        return {
            "ok": False,
            "message": str(e)
        }


# =========================
# HTML
# =========================

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
    font-family:
        Tahoma,
        Arial,
        sans-serif;

    background:
        radial-gradient(
            circle at top,
            #102b45 0,
            #07111d 45%,
            #040912 100%
        );

    color:#fff;
    min-height:100vh;
}

.container{
    width:min(900px,94%);
    margin:40px auto;
}

.header{
    text-align:center;
    margin-bottom:25px;
}

.logo{
    width:70px;
    height:70px;
    margin:auto;

    display:flex;
    align-items:center;
    justify-content:center;

    border-radius:22px;

    background:
        linear-gradient(
            135deg,
            #00e5ff,
            #0077ff
        );

    color:#00111d;
    font-size:32px;
    font-weight:bold;

    box-shadow:
        0 0 35px rgba(0,229,255,.35);
}

h1{
    margin:15px 0 5px;
    font-size:30px;
}

.subtitle{
    color:#91a8bd;
}

.card{
    background:
        rgba(9,23,38,.88);

    border:1px solid
        rgba(0,229,255,.12);

    border-radius:22px;

    padding:22px;

    margin-bottom:18px;

    box-shadow:
        0 15px 45px rgba(0,0,0,.25);
}

.card h2{
    margin-top:0;
    font-size:19px;
}

label{
    display:block;
    margin:12px 0 7px;
    color:#9db1c4;
}

input,
textarea{
    width:100%;

    background:#071421;

    border:1px solid #20394e;

    color:white;

    padding:13px;

    border-radius:13px;

    outline:none;

    font-size:15px;
}

input:focus,
textarea:focus{
    border-color:#00d9ff;
}

textarea{
    resize:vertical;
    min-height:100px;
}

button{
    border:0;

    padding:13px 18px;

    border-radius:13px;

    background:
        linear-gradient(
            135deg,
            #00d9ff,
            #0088ff
        );

    color:#00131d;

    font-weight:bold;

    cursor:pointer;

    margin-top:14px;
}

button.secondary{
    background:#152a3b;
    color:#d9f8ff;
}

button:hover{
    transform:translateY(-1px);
}

.status{
    padding:14px;
    border-radius:13px;
    margin-top:15px;

    background:#081724;

    color:#91a8bd;
}

.success{
    color:#58f2ad;
}

.error{
    color:#ff7070;
}

.chatbox{
    display:flex;
    gap:10px;
    align-items:center;
}

.chatbox input{
    flex:1;
}

.copy{
    margin-top:0;
    white-space:nowrap;
}

.bot-info{
    line-height:2;
    color:#b7c9d8;
}

.badge{
    display:inline-block;

    background:
        rgba(0,229,255,.1);

    color:#50e9ff;

    padding:5px 10px;

    border-radius:20px;

    font-size:12px;
}

.hidden{
    display:none;
}

.footer{
    text-align:center;
    color:#61778b;
    margin:30px 0;
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
            ساخت و مدیریت ربات روبیکا
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
            placeholder="توکن ربات روبیکا را وارد کنید"
        >

        <button onclick="connectBot()">
            اتصال و پیدا کردن chat_id
        </button>

        <div
            id="status"
            class="status"
        >
            ربات هنوز متصل نشده است.
        </div>

    </div>


    <!-- اطلاعات -->

    <div
        id="infoCard"
        class="card hidden"
    >

        <h2>
            🤖 اطلاعات ربات
        </h2>

        <div
            id="botInfo"
            class="bot-info"
        ></div>

    </div>


    <!-- Chat ID -->

    <div
        id="chatCard"
        class="card"
    >

        <h2>
            💬 chat_id
        </h2>

        <p style="color:#8ea5b8">
            یک پیام مثل <b>/start</b> برای ربات بفرستید؛
            chat_id به صورت خودکار اینجا نمایش داده می‌شود.
        </p>

        <div class="chatbox">

            <input
                id="chatId"
                readonly
                placeholder="در انتظار پیام..."
            >

            <button
                class="copy secondary"
                onclick="copyChatId()"
            >
                کپی
            </button>

        </div>

        <div
            id="chatStatus"
            class="status"
        >
            در انتظار پیام جدید...
        </div>

    </div>


    <!-- ارسال پیام -->

    <div class="card">

        <h2>
            ✉️ ارسال پیام آزمایشی
        </h2>

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
            آماده ارسال
        </div>

    </div>


    <div class="footer">
        ساخته شده با ❤️ برای پتی
    </div>

</div>


<script>

let currentToken = "";

let pollTimer = null;


/* =========================
   اتصال ربات
========================= */

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
            "لطفاً توکن ربات را وارد کنید.";

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
            "✅ ربات متصل شد. حالا یک پیام برای ربات بفرستید.";

        showBotInfo(result.bot);

        if(result.chat_id){

            setChatId(result.chat_id);

        }

        startPolling();

    }catch(error){

        status.className =
            "status error";

        status.innerText =
            "خطا در ارتباط با سرور.";

        console.error(error);
    }
}


/* =========================
   نمایش اطلاعات ربات
========================= */

function showBotInfo(bot){

    const card =
        document
        .getElementById("infoCard");

    const box =
        document
        .getElementById("botInfo");

    card.classList.remove("hidden");

    if(!bot){

        box.innerHTML =
            "اطلاعات ربات دریافت شد.";

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

    box.innerHTML = `
        <div>
            نام:
            <span class="badge">
                ${escapeHtml(name)}
            </span>
        </div>

        <div>
            username:
            <span class="badge">
                ${escapeHtml(username)}
            </span>
        </div>
    `;
}


/* =========================
   گرفتن chat_id
========================= */

async function pollChatId(){

    if(!currentToken){
        return;
    }

    try{

        const response =
            await fetch(
                "/api/chat-id?token=" +
                encodeURIComponent(currentToken)
            );

        const result =
            await response.json();

        if(result.ok && result.chat_id){

            setChatId(result.chat_id);

            const status =
                document
                .getElementById("chatStatus");

            status.className =
                "status success";

            status.innerText =
                "✅ chat_id با موفقیت پیدا شد.";

            stopPolling();
        }

    }catch(error){

        console.log(error);
    }
}


function startPolling(){

    stopPolling();

    pollTimer =
        setInterval(
            pollChatId,
            2000
        );

    pollChatId();
}


function stopPolling(){

    if(pollTimer){

        clearInterval(pollTimer);

        pollTimer = null;
    }
}


/* =========================
   نمایش chat_id
========================= */

function setChatId(chatId){

    document
        .getElementById("chatId")
        .value = chatId;

    localStorage.setItem(
        "peti_chat_id",
        chatId
    );
}


/* =========================
   کپی
========================= */

async function copyChatId(){

    const input =
        document
        .getElementById("chatId");

    if(!input.value){

        alert(
            "هنوز chat_id پیدا نشده است."
        );

        return;
    }

    try{

        await navigator.clipboard.writeText(
            input.value
        );

        alert(
            "chat_id کپی شد."
        );

    }catch(error){

        input.select();

        document.execCommand("copy");

        alert(
            "chat_id کپی شد."
        );
    }
}


/* =========================
   ارسال پیام
========================= */

async function sendMessage(){

    const token =
        currentToken ||
        document
        .getElementById("token")
        .value
        .trim();

    const chatId =
        document
        .getElementById("chatId")
        .value
        .trim();

    const text =
        document
        .getElementById("message")
        .value
        .trim();

    const status =
        document
        .getElementById("sendStatus");

    if(!token){

        status.className =
            "status error";

        status.innerText =
            "ابتدا ربات را متصل کنید.";

        return;
    }

    if(!chatId){

        status.className =
            "status error";

        status.innerText =
            "ابتدا یک پیام برای ربات بفرستید تا chat_id پیدا شود.";

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
                        token:token,
                        chat_id:chatId,
                        text:text
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
                "ارسال پیام ناموفق بود.";
        }

    }catch(error){

        status.className =
            "status error";

        status.innerText =
            "خطا در ارتباط با سرور.";

        console.error(error);
    }
}


/* =========================
   جلوگیری از XSS
========================= */

function escapeHtml(value){

    return String(value)
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");
}


/* =========================
   بازیابی chat_id
========================= */

window.addEventListener(
    "load",
    () => {

        const saved =
            localStorage.getItem(
                "peti_chat_id"
            );

        if(saved){

            setChatId(saved);
        }

    }
);

</script>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


# =========================
# Run
# =========================

if __name__ == "__main__":

    import uvicorn

    port = 8000

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
)
