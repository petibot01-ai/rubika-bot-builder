# ============================================================
# پتی ربات‌ساز روبیکا - نسخه تک فایلی
# فایل: app.py
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import requests
import re


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Peti Rubika Bot Builder"
)


# ============================================================
# RUBIKA API
# ============================================================

RUBIKA_API = "https://botapi.rubika.ir/v3"


# ============================================================
# MODELS
# ============================================================

class TokenRequest(BaseModel):
    token: str = Field(
        min_length=5,
        max_length=500
    )


class SendMessageRequest(BaseModel):
    token: str = Field(
        min_length=5,
        max_length=500
    )

    chat_id: str = Field(
        min_length=1,
        max_length=200
    )

    text: str = Field(
        min_length=1,
        max_length=4096
    )


# ============================================================
# TOKEN
# ============================================================

def validate_token(token: str):

    token = token.strip()

    if not token:
        raise HTTPException(
            status_code=400,
            detail="توکن وارد نشده است."
        )

    # جلوگیری از ارسال ورودی‌های عجیب به URL
    if not re.fullmatch(
        r"[A-Za-z0-9._:-]+",
        token
    ):
        raise HTTPException(
            status_code=400,
            detail="فرمت توکن صحیح نیست."
        )

    return token


# ============================================================
# RUBIKA REQUEST
# ============================================================

def rubika_request(
    token: str,
    method: str,
    data: dict
):

    token = validate_token(token)

    url = f"{RUBIKA_API}/{token}/{method}"

    try:

        response = requests.post(
            url,
            json=data,
            timeout=15
        )

    except requests.RequestException:

        raise HTTPException(
            status_code=502,
            detail="ارتباط با سرور روبیکا برقرار نشد."
        )

    if response.status_code >= 400:

        raise HTTPException(
            status_code=400,
            detail=(
                "درخواست توسط روبیکا رد شد. "
                f"HTTP {response.status_code}"
            )
        )

    try:

        result = response.json()

    except ValueError:

        raise HTTPException(
            status_code=502,
            detail="پاسخ روبیکا معتبر نیست."
        )

    # وضعیت API
    if result.get("status") not in (None, "OK"):

        error = result.get(
            "error",
            "درخواست نامعتبر است."
        )

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    return result


# ============================================================
# VERIFY TOKEN
# ============================================================

@app.post("/api/verify-token")
def verify_token(request: TokenRequest):

    result = rubika_request(
        request.token,
        "getMe",
        {}
    )

    bot = {}

    if isinstance(result.get("data"), dict):

        bot = result["data"].get(
            "bot",
            {}
        )

    if not bot:

        bot = result.get(
            "bot",
            {}
        )

    return {
        "ok": True,
        "bot": bot
    }


# ============================================================
# SEND MESSAGE
# ============================================================

@app.post("/api/send-message")
def send_message(
    request: SendMessageRequest
):

    result = rubika_request(

        request.token,

        "sendMessage",

        {
            "chat_id": request.chat_id,
            "text": request.text
        }
    )

    return {
        "ok": True,
        "result": result
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "Peti Rubika Bot Builder"
    }


# ============================================================
# WEBSITE
# ============================================================

HTML = r"""
<!DOCTYPE html>

<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1.0"
>

<title>
پتی ربات‌ساز روبیکا
</title>


<style>

*{
    box-sizing:border-box;
}


html{
    scroll-behavior:smooth;
}


body{

    margin:0;

    background:#030917;

    color:#edf5ff;

    font-family:
        Tahoma,
        Arial,
        sans-serif;
}


button,
input,
textarea{

    font-family:inherit;

}


button{

    cursor:pointer;

}


/* =========================================================
   APP
========================================================= */

.app{

    min-height:100vh;

    background:

        radial-gradient(
            circle at 50% -10%,
            #0b3150 0,
            #030917 42%
        ),

        linear-gradient(
            #030917,
            #030917
        );

}


/* =========================================================
   CONTAINER
========================================================= */

.container{

    width:min(
        1100px,
        92%
    );

    margin:auto;

    padding-bottom:80px;

}


/* =========================================================
   HEADER
========================================================= */

header{

    height:76px;

    display:flex;

    justify-content:space-between;

    align-items:center;

    border-bottom:
        1px solid #10324a;

}


.brand{

    display:flex;

    align-items:center;

    gap:12px;

    font-size:21px;

    font-weight:900;

}


.logo{

    width:44px;

    height:44px;

    display:grid;

    place-items:center;

    border-radius:14px;

    color:#20d8ff;

    background:#061b30;

    border:
        1px solid #18c9ef;

    box-shadow:
        0 0 30px #00d9ff18;

}


.online{

    padding:
        8px
        13px;

    border-radius:100px;

    color:#32dda0;

    background:#06251d;

    border:
        1px solid #14634d;

    font-size:12px;

}


/* =========================================================
   HERO
========================================================= */

.hero{

    padding:
        70px
        0
        40px;

}


.badge{

    display:inline-block;

    padding:
        7px
        13px;

    border-radius:100px;

    color:#20d8ff;

    background:#062036;

    border:
        1px solid #15506a;

    font-size:12px;

}


.hero h1{

    margin:
        18px
        0
        12px;

    font-size:
        clamp(
            38px,
            7vw,
            65px
        );

    line-height:1.15;

}


.blue{

    color:#1bd6ff;

}


.hero p{

    max-width:750px;

    color:#8095b9;

    font-size:17px;

    line-height:2;

}


/* =========================================================
   LAYOUT
========================================================= */

.layout{

    display:grid;

    grid-template-columns:
        1.25fr
        .75fr;

    gap:20px;

}


/* =========================================================
   CARD
========================================================= */

.card{

    padding:25px;

    background:#071226e8;

    border:
        1px solid #10364f;

    border-radius:25px;

    box-shadow:
        0 25px 70px #0008;

}


.card h2{

    margin-top:0;

}


/* =========================================================
   FORM
========================================================= */

label{

    display:block;

    margin:
        18px
        0
        7px;

    color:#91a8cb;

    font-size:13px;

}


input,
textarea{

    width:100%;

    padding:14px;

    color:white;

    background:#030b19;

    border:
        1px solid #153a54;

    border-radius:14px;

    outline:none;

    transition:.2s;

}


input:focus,
textarea:focus{

    border-color:#19d1f4;

    box-shadow:
        0 0 0 3px #19d1f418;

}


/* =========================================================
   BUTTONS
========================================================= */

.actions{

    display:flex;

    flex-wrap:wrap;

    gap:10px;

    margin-top:20px;

}


button{

    padding:
        13px
        19px;

    border-radius:14px;

    font-weight:800;

}


.primary{

    color:white;

    border:
        1px solid #31ddff;

    background:

        linear-gradient(
            180deg,
            #15cce9,
            #087da8
        );

}


.secondary{

    color:#bed1eb;

    background:#08192c;

    border:
        1px solid #17435d;

}


/* =========================================================
   STATUS
========================================================= */

.status{

    margin-top:18px;

    padding:14px;

    border-radius:14px;

    background:#041322;

    border:
        1px solid #123650;

    color:#8ea6c8;

    line-height:1.8;

}


.success{

    color:#36e0a2;

}


.error{

    color:#ff637f;

}


/* =========================================================
   BOT INFO
========================================================= */

.info-row{

    display:flex;

    justify-content:space-between;

    gap:20px;

    padding:15px 0;

    border-bottom:
        1px solid #102d44;

    color:#8da4c7;

}


.info-row strong{

    color:white;

    text-align:left;

}


.commands{

    margin-top:20px;

    display:grid;

    gap:10px;

}


.command{

    display:flex;

    align-items:center;

    justify-content:space-between;

    padding:14px;

    background:#030b19;

    border:
        1px solid #10334c;

    border-radius:15px;

}


.command code{

    color:#20d7ff;

    font-size:15px;

}


.command span{

    color:#7186a9;

    font-size:12px;

}


/* =========================================================
   ADD COMMAND
========================================================= */

.add-command{

    display:none;

    margin-top:20px;

    padding-top:10px;

    border-top:
        1px solid #102d44;

}


.add-command.active{

    display:block;

}


/* =========================================================
   FOOTER
========================================================= */

footer{

    margin-top:50px;

    padding-top:25px;

    text-align:center;

    color:#63799e;

    border-top:
        1px solid #102c43;

    font-size:13px;

}


/* =========================================================
   MOBILE
========================================================= */

@media(max-width:800px){

    .layout{

        grid-template-columns:1fr;

    }

    .online{

        display:none;

    }

    .hero{

        padding-top:45px;

    }

}

</style>

</head>


<body>


<div class="app">

<div class="container">


<!-- =====================================================
     HEADER
===================================================== -->

<header>

    <div class="brand">

        <div class="logo">
            پ
        </div>

        پتی ربات‌ساز

    </div>


    <div class="online">

        ● سیستم آماده است

    </div>

</header>


<!-- =====================================================
     HERO
===================================================== -->

<section class="hero">

    <span class="badge">

        ربات‌ساز حرفه‌ای روبیکا

    </span>


    <h1>

        ساخت ربات

        <span class="blue">

            روبیکا

        </span>

    </h1>


    <p>

        توکن رباتت را وارد کن و ربات خودت را
        مستقیماً از پنل پتی مدیریت کن.

        اتصال از طریق سرور انجام می‌شود و
        توکن داخل کد JavaScript قرار نمی‌گیرد.

    </p>

</section>


<!-- =====================================================
     MAIN
===================================================== -->

<div class="layout">


<!-- =====================================================
     CONNECTION CARD
===================================================== -->

<section class="card">

    <h2>

        🔗 اتصال ربات

    </h2>


    <label>

        توکن ربات روبیکا

    </label>


    <input

        id="token"

        type="password"

        autocomplete="off"

        placeholder="توکن ربات را وارد کنید"

    >


    <label>

        شناسه چت برای تست پیام

    </label>


    <input

        id="chatId"

        placeholder="chat_id"

    >


    <label>

        متن پیام تست

    </label>


    <textarea

        id="message"

        rows="4"

    >سلام! 👋 این پیام از پتی ارسال شد.</textarea>


    <div class="actions">


        <button

            class="primary"

            onclick="connectBot()"

        >

            🔗 اتصال و بررسی

        </button>


        <button

            class="secondary"

            onclick="sendMessage()"

        >

            📨 ارسال پیام

        </button>


    </div>


    <div

        id="status"

        class="status"

    >

        هنوز رباتی متصل نشده است.

    </div>


</section>


<!-- =====================================================
     BOT INFORMATION
===================================================== -->

<aside class="card">


    <h2>

        🤖 اطلاعات ربات

    </h2>


    <div class="info-row">

        <span>
            وضعیت
        </span>

        <strong id="botStatus">

            قطع

        </strong>

    </div>


    <div class="info-row">

        <span>
            نام
        </span>

        <strong id="botName">

            —

        </strong>

    </div>


    <div class="info-row">

        <span>
            Username
        </span>

        <strong id="botUsername">

            —

        </strong>

    </div>


    <div class="info-row">

        <span>
            شناسه ربات
        </span>

        <strong id="botId">

            —

        </strong>

    </div>


    <h3>

        دستورات ربات

    </h3>


    <div

        id="commands"

        class="commands"

    >

        <div class="command">

            <code>
                /start
            </code>

            <span>
                شروع ربات
            </span>

        </div>


        <div class="command">

            <code>
                /help
            </code>

            <span>
                نمایش راهنما
            </span>

        </div>

    </div>


    <button

        class="secondary"

        style="
            margin-top:15px;
            width:100%;
        "

        onclick="toggleCommandBox()"

    >

        + افزودن دستور

    </button>


    <div

        id="addCommandBox"

        class="add-command"

    >

        <label>
            دستور
        </label>


        <input

            id="newCommand"

            placeholder="/about"

        >


        <label>
            توضیح
        </label>


        <input

            id="newDescription"

            placeholder="درباره ربات"

        >


        <button

            class="primary"

            style="
                margin-top:12px;
                width:100%;
            "

            onclick="addCommand()"

        >

            افزودن دستور

        </button>

    </div>


</aside>


</div>


<footer>

    پتی ربات‌ساز روبیکا

    <br>

    طراحی اختصاصی با سبک مدرن و نئونی

</footer>


</div>

</div>


<script>


// =========================================================
// API REQUEST
// =========================================================

async function apiRequest(
    url,
    data
){

    const response =
        await fetch(

            url,

            {

                method:"POST",

                headers:{
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify(data)

            }

        );


    const result =
        await response
        .json()
        .catch(
            () => ({
                detail:
                    "پاسخ سرور نامعتبر است."
            })
        );


    if(!response.ok){

        throw new Error(

            result.detail ||
            "خطایی رخ داد."

        );

    }


    return result;

}


// =========================================================
// STATUS
// =========================================================

function setStatus(
    text,
    type=""
){

    const element =
        document.getElementById(
            "status"
        );


    element.textContent =
        text;


    element.className =
        "status " + type;

}


// =========================================================
// CONNECT BOT
// =========================================================

async function connectBot(){

    const token =
        document
        .getElementById(
            "token"
        )
        .value
        .trim();


    if(!token){

        setStatus(
            "لطفاً توکن ربات را وارد کنید.",
            "error"
        );

        return;

    }


    setStatus(
        "⏳ در حال بررسی توکن..."
    );


    try{

        const result =
            await apiRequest(

                "/api/verify-token",

                {
                    token:token
                }

            );


        const bot =
            result.bot || {};


        document
        .getElementById(
            "botStatus"
        )
        .textContent =
            "متصل ✓";


        document
        .getElementById(
            "botStatus"
        )
        .className =
            "success";


        document
        .getElementById(
            "botName"
        )
        .textContent =
            bot.name ||
            bot.first_name ||
            "—";


        document
        .getElementById(
            "botUsername"
        )
        .textContent =
            bot.username ||
            "—";


        document
        .getElementById(
            "botId"
        )
        .textContent =
            bot.bot_id ||
            bot.id ||
            "—";


        setStatus(
            "✅ ربات با موفقیت به پتی متصل شد.",
            "success"
        );

    }

    catch(error){

        document
        .getElementById(
            "botStatus"
        )
        .textContent =
            "خطا";


        document
        .getElementById(
            "botStatus"
        )
        .className =
            "error";


        setStatus(
            "❌ " + error.message,
            "error"
        );

    }

}


// =========================================================
// SEND MESSAGE
// =========================================================

async function sendMessage(){

    const token =
        document
        .getElementById(
            "token"
        )
        .value
        .trim();


    const chatId =
        document
        .getElementById(
            "chatId"
        )
        .value
        .trim();


    const text =
        document
        .getElementById(
            "message"
        )
        .value;


    if(!token){

        setStatus(
            "توکن را وارد کنید.",
            "error"
        );

        return;

    }


    if(!chatId){

        setStatus(
            "chat_id را وارد کنید.",
            "error"
        );

        return;

    }


    if(!text.trim()){

        setStatus(
            "متن پیام خالی است.",
            "error"
        );

        return;

    }


    setStatus(
        "⏳ در حال ارسال پیام..."
    );


    try{

        await apiRequest(

            "/api/send-message",

            {

                token:token,

                chat_id:chatId,

                text:text

            }

        );


        setStatus(
            "✅ پیام با موفقیت از طریق روبیکا ارسال شد.",
            "success"
        );

    }

    catch(error){

        setStatus(
            "❌ " + error.message,
            "error"
        );

    }

}


// =========================================================
// COMMAND BOX
// =========================================================

function toggleCommandBox(){

    document
    .getElementById(
        "addCommandBox"
    )
    .classList.toggle(
        "active"
    );

}


// =========================================================
// ADD COMMAND
// =========================================================

function addCommand(){

    const command =
        document
        .getElementById(
            "newCommand"
        )
        .value
        .trim();


    const description =
        document
        .getElementById(
            "newDescription"
        )
        .value
        .trim();


    if(!command){

        alert(
            "دستور را وارد کنید."
        );

        return;

    }


    const box =
        document
        .getElementById(
            "commands"
        );


    const item =
        document.createElement(
            "div"
        );


    item.className =
        "command";


    const code =
        document.createElement(
            "code"
        );


    code.textContent =
        command;


    const span =
        document.createElement(
            "span"
        );


    span.textContent =
        description ||
        "دستور سفارشی";


    item.appendChild(code);

    item.appendChild(span);

    box.appendChild(item);


    document
    .getElementById(
        "newCommand"
    )
    .value = "";


    document
    .getElementById(
        "newDescription"
    )
    .value = "";

}


// =========================================================
// ENTER KEY
// =========================================================

document
.getElementById("token")
.addEventListener(
    "keydown",
    function(event){

        if(
            event.key ===
            "Enter"
        ){

            connectBot();

        }

    }
);

</script>


</body>

</html>
"""


# ============================================================
# WEBSITE ROUTE
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    return HTML


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "app:app",

        host="0.0.0.0",

        port=8000,

        reload=True

  )
