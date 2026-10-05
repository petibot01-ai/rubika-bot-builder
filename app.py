import os
import time
import threading
import requests

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn


# =========================================================
# PETI RUBIKA BOT BUILDER
# Single File Version
# =========================================================

app = FastAPI(title="Peti Bot Builder")

API_BASE = "https://botapi.rubika.ir/v3"

# توکن‌ها فقط در حافظه نگهداری می‌شوند
# برای امنیت، توکن را داخل کد ننویس.
bots = {}


# =========================================================
# RUBIKA API
# =========================================================

def rubika_request(token: str, method: str, data: dict | None = None):
    """
    درخواست به API ربات روبیکا
    """
    url = f"{API_BASE}/{token}/{method}"

    try:
        response = requests.post(
            url,
            json=data or {},
            timeout=20
        )

        text = response.text

        try:
            result = response.json()
        except Exception:
            return {
                "ok": False,
                "error": "پاسخ API به صورت JSON نبود",
                "http_status": response.status_code,
                "raw": text[:1000]
            }

        # بعضی نسخه‌های API از status استفاده می‌کنند
        if isinstance(result, dict):
            if result.get("status") == "OK":
                return {
                    "ok": True,
                    "data": result
                }

            # بعضی پاسخ‌ها ممکن است data داشته باشند
            if "data" in result and result.get("status") not in ["ERROR", "FAILED"]:
                return {
                    "ok": True,
                    "data": result
                }

        return {
            "ok": False,
            "http_status": response.status_code,
            "error": result
        }

    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": "اتصال به سرور روبیکا Timeout شد."
        }

    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "اتصال به سرور روبیکا برقرار نشد."
        }

    except Exception as e:
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


def get_updates(token: str, offset_id=None):
    data = {
        "limit": 100
    }

    if offset_id:
        data["offset_id"] = offset_id

    return rubika_request(
        token,
        "getUpdates",
        data
    )


# =========================================================
# MODELS
# =========================================================

class TokenRequest(BaseModel):
    token: str


class SendMessageRequest(BaseModel):
    token: str
    chat_id: str
    text: str


class SaveBotRequest(BaseModel):
    token: str


# =========================================================
# API ROUTES
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Peti Bot Builder"
    }


@app.post("/api/verify-token")
def verify_token(data: TokenRequest):

    token = data.token.strip()

    if not token:
        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    if len(token) > 500:
        return {
            "ok": False,
            "message": "توکن نامعتبر است."
        }

    result = get_me(token)

    if not result["ok"]:
        return {
            "ok": False,
            "message": "توکن معتبر نیست یا API روبیکا درخواست را قبول نکرد.",
            "details": result
        }

    bot_data = result.get("data", {})

    bots[token] = {
        "token": token,
        "bot": bot_data,
        "offset_id": None
    }

    return {
        "ok": True,
        "message": "اتصال با موفقیت انجام شد.",
        "bot": bot_data
    }


@app.post("/api/send-message")
def api_send_message(data: SendMessageRequest):

    token = data.token.strip()
    chat_id = data.chat_id.strip()
    text = data.text.strip()

    if not token:
        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    if not chat_id:
        return {
            "ok": False,
            "message": "chat_id وارد نشده است."
        }

    if not text:
        return {
            "ok": False,
            "message": "متن پیام خالی است."
        }

    result = send_message(
        token,
        chat_id,
        text
    )

    if not result["ok"]:
        return {
            "ok": False,
            "message": "ارسال پیام ناموفق بود.",
            "details": result
        }

    return {
        "ok": True,
        "message": "پیام با موفقیت ارسال شد.",
        "result": result
    }


# =========================================================
# SIMPLE BOT POLLING
# =========================================================

def extract_update_text(update):
    """
    تلاش می‌کند متن و chat_id را از ساختارهای مختلف Update پیدا کند.
    """

    if not isinstance(update, dict):
        return None, None

    chat_id = update.get("chat_id")
    text = update.get("text")

    new_message = update.get("new_message")

    if isinstance(new_message, dict):

        if not chat_id:
            chat_id = new_message.get("chat_id")

        if not text:
            text = new_message.get("text")

    message = update.get("message")

    if isinstance(message, dict):

        if not chat_id:
            chat_id = message.get("chat_id")

        if not text:
            text = message.get("text")

    return text, chat_id


def bot_worker(token):

    offset_id = None

    while True:

        try:

            result = get_updates(
                token,
                offset_id
            )

            if not result["ok"]:
                time.sleep(10)
                continue

            response = result.get("data", {})

            updates = []

            if isinstance(response, dict):

                data = response.get("data")

                if isinstance(data, dict):
                    updates = data.get("updates", []) or []

                if not updates:
                    updates = response.get("updates", []) or []

            if not isinstance(updates, list):
                updates = []

            for update in updates:

                text, chat_id = extract_update_text(update)

                # پیدا کردن offset
                if isinstance(update, dict):

                    update_id = (
                        update.get("update_id")
                        or update.get("id")
                        or update.get("message_id")
                    )

                    if update_id:
                        offset_id = str(update_id)

                if not text or not chat_id:
                    continue

                text = str(text).strip()

                # پاسخ ساده به /start
                if text == "/start":
                    send_message(
                        token,
                        str(chat_id),
                        "سلام 👋\nبه ربات پتی خوش آمدید."
                    )

                # پاسخ به /help
                elif text == "/help":
                    send_message(
                        token,
                        str(chat_id),
                        "دستورات ربات:\n\n/start\n/help"
                    )

            time.sleep(2)

        except Exception:
            time.sleep(10)


@app.post("/api/start-bot")
def start_bot(data: SaveBotRequest):

    token = data.token.strip()

    if not token:
        return {
            "ok": False,
            "message": "توکن وارد نشده است."
        }

    result = get_me(token)

    if not result["ok"]:
        return {
            "ok": False,
            "message": "ابتدا توکن را بررسی کنید.",
            "details": result
        }

    if token not in bots:

        bots[token] = {
            "token": token,
            "bot": result.get("data", {}),
            "offset_id": None
        }

        thread = threading.Thread(
            target=bot_worker,
            args=(token,),
            daemon=True
        )

        thread.start()

    return {
        "ok": True,
        "message": "ربات فعال شد."
    }


# =========================================================
# FRONTEND
# =========================================================

HTML = r"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0"
>

<title>پتی ربات‌ساز روبیکا</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:#061426;
    color:#eef8ff;
    font-family:
        Tahoma,
        Arial,
        sans-serif;
}

.container{
    width:min(900px,94%);
    margin:auto;
    padding:25px 0 60px;
}

.header{
    display:flex;
    justify-content:space-between;
    align-items:center;
    border-bottom:1px solid #123451;
    padding:15px 5px 25px;
    margin-bottom:35px;
}

.logo{
    width:55px;
    height:55px;
    border:2px solid #16c9ff;
    border-radius:18px;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#16c9ff;
    font-size:25px;
    font-weight:bold;
}

.brand{
    font-size:25px;
    font-weight:bold;
}

.hero{
    text-align:center;
    margin-bottom:35px;
}

.badge{
    display:inline-block;
    border:1px solid #14527a;
    border-radius:30px;
    padding:10px 20px;
    color:#16c9ff;
}

h1{
    font-size:44px;
    margin:35px 0 20px;
}

h1 span{
    color:#13c9ff;
}

.description{
    color:#9bb0c8;
    font-size:19px;
    line-height:2;
}

.card{
    background:#061325;
    border:1px solid #123b5c;
    border-radius:30px;
    padding:35px;
    margin-top:25px;
    box-shadow:0 10px 35px #0005;
}

.card h2{
    margin-top:0;
    font-size:28px;
}

label{
    display:block;
    margin:22px 0 9px;
    color:#a8bdd2;
}

input, textarea{
    width:100%;
    background:#020c19;
    color:white;
    border:1px solid #194563;
    border-radius:18px;
    padding:18px;
    font-size:16px;
    outline:none;
}

input:focus,
textarea:focus{
    border-color:#16c9ff;
    box-shadow:0 0 0 2px #16c9ff22;
}

textarea{
    min-height:130px;
    resize:vertical;
}

.buttons{
    display:flex;
    gap:15px;
    margin-top:22px;
}

button{
    flex:1;
    padding:17px;
    border-radius:18px;
    border:1px solid #16506d;
    background:#071b2d;
    color:#c6def0;
    font-size:17px;
    cursor:pointer;
}

button.primary{
    background:linear-gradient(135deg,#0dc4f0,#087ba8);
    color:white;
    border-color:#20d4ff;
}

button:hover{
    filter:brightness(1.15);
}

.status{
    margin-top:20px;
    border-radius:18px;
    padding:18px;
    display:none;
    line-height:1.9;
}

.success{
    display:block;
    background:#06261e;
    border:1px solid #13c993;
    color:#55e8bd;
}

.error{
    display:block;
    background:#2b0710;
    border:1px solid #ff4662;
    color:#ff7185;
}

.bot-info{
    display:none;
}

.info-row{
    display:flex;
    justify-content:space-between;
    padding:17px 0;
    border-bottom:1px solid #12304a;
}

.value{
    color:#fff;
}

.commands{
    margin-top:20px;
}

.command{
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding:15px;
    background:#081a2b;
    border:1px solid #123b58;
    border-radius:15px;
    margin-bottom:10px;
}

.command code{
    color:#19ccff;
}

.footer{
    text-align:center;
    color:#617990;
    margin-top:40px;
}

@media(max-width:600px){

    .container{
        width:92%;
    }

    h1{
        font-size:34px;
    }

    .card{
        padding:22px;
        border-radius:24px;
    }

    .buttons{
        flex-direction:column;
    }

}

</style>

</head>

<body>

<div class="container">

<header class="header">

<div class="brand">
پتی ربات‌ساز
</div>

<div class="logo">
پ
</div>

</header>


<section class="hero">

<div class="badge">
ربات‌ساز حرفه‌ای روبیکا
</div>

<h1>
ساخت ربات <span>روبیکا</span>
</h1>

<div class="description">
توکن رباتت را وارد کن و ربات خودت را مستقیماً از پنل پتی مدیریت کن.
<br>
اتصال و ارسال پیام از طریق سرور انجام می‌شود.
</div>

</section>


<div class="card">

<h2>
🔗 اتصال ربات
</h2>

<label>
توکن ربات روبیکا
</label>

<input
id="token"
type="password"
placeholder="توکن ربات را وارد کنید"
/>


<label>
شناسه چت برای تست پیام
</label>

<input
id="chat_id"
placeholder="chat_id"
/>


<label>
متن پیام تست
</label>

<textarea id="message">سلام! 👋
این پیام از پتی ارسال شد.</textarea>


<div class="buttons">

<button
class="primary"
onclick="verifyToken()"
>
🔗 اتصال و بررسی
</button>

<button
onclick="sendMessage()"
>
✉️ ارسال پیام
</button>

</div>


<div id="status" class="status"></div>

</div>


<div
id="botInfo"
class="card bot-info"
>

<h2>
🤖 اطلاعات ربات
</h2>

<div class="info-row">
<span>وضعیت</span>
<strong
id="botStatus"
class="value"
>
قطع
</strong>
</div>

<div class="info-row">
<span>نام</span>
<strong
id="botName"
class="value"
>
-
</strong>
</div>

<div class="info-row">
<span>شناسه</span>
<strong
id="botId"
class="value"
>
-
</strong>
</div>

<div class="commands">

<h3>
دستورات فعال
</h3>

<div class="command">
<code>/start</code>
<span>پیام خوش‌آمدگویی</span>
</div>

<div class="command">
<code>/help</code>
<span>نمایش راهنما</span>
</div>

</div>

<div class="buttons">

<button
class="primary"
onclick="startBot()"
>
🚀 فعال‌سازی ربات
</button>

</div>

</div>


<div class="footer">
پتی • ربات‌ساز روبیکا
</div>

</div>


<script>

function showStatus(message, type){

    const box = document.getElementById("status");

    box.className = "status " + type;

    box.innerText = message;

}


function getToken(){

    return document
        .getElementById("token")
        .value
        .trim();

}


async function verifyToken(){

    const token = getToken();

    if(!token){

        showStatus(
            "❌ لطفاً توکن ربات را وارد کنید.",
            "error"
        );

        return;
    }

    showStatus(
        "⏳ در حال بررسی توکن...",
        "success"
    );

    try{

        const response = await fetch(
            "/api/verify-token",
            {
                method:"POST",
                headers:{
                    "Content-Type":"application/json"
                },
                body:JSON.stringify({
                    token:token
                })
            }
        );

        const data = await response.json();

        if(!data.ok){

            console.log(data);

            showStatus(
                "❌ " +
                (data.message || "توکن نامعتبر است.") +
                "\n\nجزئیات در Console مرورگر موجود است.",
                "error"
            );

            return;
        }

        const bot = data.bot || {};
        const botData = bot.data || bot;

        document.getElementById("botInfo").style.display = "block";

        document.getElementById("botStatus").innerText =
            "متصل ✓";

        document.getElementById("botStatus").style.color =
            "#35e6b3";

        document.getElementById("botName").innerText =
            botData.name ||
            botData.username ||
            "-";

        document.getElementById("botId").innerText =
            botData.bot_id ||
            botData.id ||
            "-";

        showStatus(
            "✅ اتصال با موفقیت انجام شد.",
            "success"
        );

    }catch(error){

        showStatus(
            "❌ خطا در اتصال به سرور پتی.",
            "error"
        );

        console.error(error);
    }
}


async function sendMessage(){

    const token = getToken();

    const chat_id =
        document
        .getElementById("chat_id")
        .value
        .trim();

    const text =
        document
        .getElementById("message")
        .value
        .trim();

    if(!token){

        showStatus(
            "❌ ابتدا توکن را وارد کنید.",
            "error"
        );

        return;
    }

    if(!chat_id){

        showStatus(
            "❌ chat_id را وارد کنید.",
            "error"
        );

        return;
    }

    if(!text){

        showStatus(
            "❌ متن پیام خالی است.",
            "error"
        );

        return;
    }

    showStatus(
        "⏳ در حال ارسال پیام...",
        "success"
    );

    try{

        const response = await fetch(
            "/api/send-message",
            {
                method:"POST",
                headers:{
                    "Content-Type":"application/json"
                },
                body:JSON.stringify({
                    token:token,
                    chat_id:chat_id,
                    text:text
                })
            }
        );

        const data = await response.json();

        if(!data.ok){

            console.log(data);

            showStatus(
                "❌ ارسال پیام انجام نشد.\n" +
                "جزئیات خطا در Console موجود است.",
                "error"
            );

            return;
        }

        showStatus(
            "✅ پیام با موفقیت ارسال شد.",
            "success"
        );

    }catch(error){

        showStatus(
            "❌ خطا در ارسال درخواست.",
            "error"
        );

        console.error(error);
    }
}


async function startBot(){

    const token = getToken();

    if(!token){

        showStatus(
            "❌ ابتدا توکن را وارد کنید.",
            "error"
        );

        return;
    }

    showStatus(
        "⏳ در حال فعال‌سازی ربات...",
        "success"
    );

    try{

        const response = await fetch(
            "/api/start-bot",
            {
                method:"POST",
                headers:{
                    "Content-Type":"application/json"
                },
                body:JSON.stringify({
                    token:token
                })
            }
        );

        const data = await response.json();

        if(!data.ok){

            showStatus(
                "❌ " + data.message,
                "error"
            );

            return;
        }

        showStatus(
            "🟢 ربات فعال شد.\n" +
            "دستورات /start و /help فعال هستند.",
            "success"
        );

    }catch(error){

        showStatus(
            "❌ خطا در فعال‌سازی ربات.",
            "error"
        );

        console.error(error);
    }
}

</script>

</body>

</html>
"""


# =========================================================
# HOME
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
