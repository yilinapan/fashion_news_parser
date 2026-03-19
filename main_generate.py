"""
main_generate.py
主程式：每週執行一次
流程：爬取時尚新聞 → Claude 生成 3 個切入點 → AI 選最自然的＋口語化改寫 → 輕量校對
     → Gemini 生圖 → 寫入 Google Sheet → Gmail 通知
"""

import os
import json
import base64
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

import anthropic
import gspread
import requests
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from news_parser import parse_feeds, build_articles_summary

# ── Google API 設定 ──────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SHEET_NAME = "IG Content Calendar"  # Google Sheet 的名稱

# ── Gmail 設定 ───────────────────────────────────────────────
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")  # 你的 Gmail
SHEET_URL = os.environ.get("SHEET_URL", "（請填入 Google Sheet 連結）")

# ── Google Drive 設定 ────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")  # 存放 IG 圖片的資料夾 ID

# ── 建立 Google 憑證 ─────────────────────────────────────────
def get_google_creds() -> Credentials:
    """Service Account 憑證（用於 Google Sheet）。"""
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


def get_drive_user_creds() -> UserCredentials:
    """用你自己的 Google 帳號憑證上傳到 Drive（解決 SA 無儲存配額問題）。"""
    creds = UserCredentials(
        token=None,
        refresh_token=os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    creds.refresh(Request())
    return creds


# ── Step 0-A：Gemini 生成圖片 ────────────────────────────────
def generate_image_gemini(prompt: str) -> bytes:
    """呼叫 Gemini 2.5 Flash 生成時尚編輯風格的圖片，回傳圖片的 bytes。"""
    api_key = os.environ["GOOGLE_AI_STUDIO_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    f"Generate a fashion editorial image: {prompt}. "
                    "Aspect ratio 4:5, 1080x1350px. "
                    "Minimalist, earth-tone palette, high-end editorial style. "
                    "No text or watermarks on the image."
                )
            }]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"]
        }
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()

    # 從回應中找到圖片資料
    candidates = resp.json().get("candidates", [])
    for candidate in candidates:
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])

    raise RuntimeError("Gemini 回應中沒有圖片資料")


# ── Step 0-B：上傳圖片到 Google Drive ────────────────────────
def upload_to_drive(creds: Credentials, image_bytes: bytes, filename: str) -> str:
    """用你自己的 Google 帳號上傳圖片到 Drive，設為公開，回傳公開連結。"""
    # 用你的帳號憑證（不是 Service Account）來上傳
    drive_creds = get_drive_user_creds()
    drive = build("drive", "v3", credentials=drive_creds)
    media = MediaInMemoryUpload(image_bytes, mimetype="image/png")

    file_metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()

    # 設定為公開可存取（Buffer 需要公開 URL）
    drive.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()

    image_url = f"https://lh3.googleusercontent.com/d/{file['id']}"
    print(f"   圖片已上傳到 Google Drive：{image_url}")
    return image_url


# ── 共用：解析 JSON helper ────────────────────────────────────
def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


# ── 載入風格檔案 ─────────────────────────────────────────────
def _load_file(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


# ── 人設與核心 System Prompt ─────────────────────────────────
PERSONA_PROMPT = """你是一個在時尚產業混了很多年的編輯，現在經營一個台灣的時尚趨勢 IG 帳號。你看秀、逛街拍、跑 showroom，對趨勢有自己的觀點但不會強迫別人接受。你的讀者是 20-35 歲、對穿搭有想法的人，你跟他們的關係像是在同一個群組裡會聊穿搭的朋友。

你寫文案的時候像在錄語音訊息給朋友，不像在寫文章。你會用小學五年級就能聽懂的日常對話方式說話。你不賣東西、不推銷、不說教。"""


STYLE_RULES = """【寫法】
- 中英文自然混搭，英文大概佔 20-30%，通常放在開頭句或關鍵詞
- 短句為主，多用句號、少用逗號
- 每句之間換行，方便手機閱讀
- 要具體：提品牌名、城市名、秀場名，不要寫「歐洲街頭」「各大品牌」這種模糊說法
- 台灣口語：「打版」不說「給版」、「顏色」不說「色」、「寬鬆」不說「鬆」
- Emoji 只能放在行末，每段最多兩個，不要塞在句子中間

【三段結構，總長 100-150 字】
第一段（Hook，1-2 句）：用一個會讓人想繼續讀的開頭切入。
第二段（3-5 句）：趨勢是什麼、為什麼值得注意。語氣像聊天。
第三段（1 句）：收尾。平淡的觀察、陳述、或問句都好，不用每次都是金句。

【Hashtag】8-12 個，中英混搭，#台灣時尚 或 #FashionTaiwan 擇一。"""


# ── Step 1：生成 3 個不同切入點的草稿 ────────────────────────
def generate_three_drafts(articles_summary: str) -> list:
    """呼叫 Claude API，根據本週趨勢文章生成 3 個不同切入點的 IG 文案草稿。"""

    style_guide = _load_file("style_guide.txt")
    fewshot_examples = _load_file("fewshot_examples.txt")

    fewshot_section = ""
    if fewshot_examples:
        fewshot_section = f"""

【風格範例——以下是長篇時尚文章，請只分析它們的「語氣、用詞、中英混搭方式」來模仿，不要模仿它們的長度和結構，你的 IG 文案仍然要維持 100-150 字短文】
{fewshot_examples}"""

    style_ref = ""
    if style_guide:
        style_ref = f"""

【參考節奏】以下品牌帳號的短句節奏和中英混搭方式可以參考（但你的定位是媒體不是品牌，不要模仿它的產品推廣語氣）：
{style_guide}"""

    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=f"""{PERSONA_PROMPT}

{STYLE_RULES}
{fewshot_section}
{style_ref}

請以 JSON 格式輸出，只輸出 JSON，不要有其他文字：
{{
  "topic": "本週趨勢主題（10字以內）",
  "drafts": [
    {{
      "angle": "切入點 A 的簡述",
      "caption": "完整文案（含 hashtag）",
      "image_prompt": "英文 AI 繪圖提示詞，時尚編輯風格，1080x1350px，4:5 直式"
    }},
    {{
      "angle": "切入點 B 的簡述",
      "caption": "完整文案（含 hashtag）",
      "image_prompt": "英文 AI 繪圖提示詞"
    }},
    {{
      "angle": "切入點 C 的簡述",
      "caption": "完整文案（含 hashtag）",
      "image_prompt": "英文 AI 繪圖提示詞"
    }}
  ],
  "hashtags": ["所有版本共用的 hashtag 列表"]
}}""",
        messages=[{
            "role": "user",
            "content": (
                f"以下是本週爬取到的時尚趨勢文章摘要：\n\n{articles_summary}\n\n"
                "請從 3 個完全不同的切入角度，各寫一篇 IG 文案。"
                "3 篇的開頭方式、敘事角度、收尾方式都要不一樣。"
            ),
        }],
    )

    return _parse_json(message.content[0].text)


# ── Step 2：AI 自動選最自然的版本 + 口語化改寫 ────────────────
def select_and_rewrite(drafts_data: dict) -> dict:
    """讓 AI 從 3 個草稿中選出最不像 AI 寫的，然後用口語化方式重寫一遍。"""

    client = anthropic.Anthropic()

    drafts_text = ""
    for i, d in enumerate(drafts_data["drafts"], 1):
        drafts_text += f"\n【版本 {i}】切入點：{d['angle']}\n{d['caption']}\n"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=f"""{PERSONA_PROMPT}

你現在要做兩件事：

1. 從以下 3 個版本中，選出「最不像 AI 寫的、最像真人在 IG 上會發的」那一個。
   判斷標準：讀起來像在跟朋友講話、沒有行銷口號感、沒有排比句、沒有刻意的轉折。

2. 選好之後，把它「口語化」——想像你在錄語音訊息傳給朋友，把那些裝腔作勢的轉折詞都拿掉，重新順一遍。
   具體來說：
   - 破折號（——）改成逗號或句號
   - 「不是 A，是 B」這種句式，直接說 B
   - 太文學的壓縮詞換成日常口語（「色」→「顏色」、「鬆」→「寬鬆」）
   - 刪掉贅字：「其實」「本身」「台灣這邊」→「台灣」
   - 每句之間換行
   - 讀起來像人在打字，不像在寫散文

請以 JSON 格式輸出，只輸出 JSON：
{{
  "selected_version": 1,
  "reason": "選這個版本的原因（一句話）",
  "topic": "{drafts_data.get('topic', '')}",
  "caption": "口語化改寫後的完整文案（含 hashtag）",
  "image_prompt": "沿用所選版本的繪圖提示詞",
  "hashtags": ["hashtag 列表"]
}}""",
        messages=[{
            "role": "user",
            "content": f"以下是同一個趨勢主題的 3 個版本，請選出最好的並口語化改寫：\n{drafts_text}"
        }],
    )

    return _parse_json(message.content[0].text)


# ── Step 3（可選）：最終校對 ──────────────────────────────────
def final_check(client: anthropic.Anthropic, content: dict) -> dict:
    """輕量校對：只抓最明顯的 AI 痕跡，不大幅改寫。"""

    caption = content.get("caption", "")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system="""你是文案校對。這篇文案已經寫得差不多了，你只需要做最後一道輕微修正。

只改以下 3 種情況，其他地方完全不動：
1. 「版型給得」→「版型打得」（台灣用語）
2. 單字詞壓縮（「色」→「顏色」、「鬆」→「寬鬆」、「沉」→「沉穩」）
3. 如果有句子唸出來不像在跟朋友講話（像在朗讀散文），稍微順一下

不要加東西、不要改結構、不要改語氣方向。改越少越好。
回傳完整 JSON，只動 caption 欄位。""",
        messages=[{
            "role": "user",
            "content": f"請做最後校對：\n\n{json.dumps(content, ensure_ascii=False, indent=2)}"
        }],
    )

    revised = _parse_json(message.content[0].text)
    content["caption"] = revised.get("caption", caption)
    return content


# ── 寫入 Google Sheet ────────────────────────────────────────
def write_to_sheet(creds: Credentials, content: dict) -> None:
    """將生成的文案寫入 Google Sheet 的第一個工作表。"""
    gc = gspread.authorize(creds)

    # 優先用 SHEET_URL 的 ID 開啟（更可靠），找不到才用名稱
    sheet_url = os.environ.get("SHEET_URL", "")
    if sheet_url and "/d/" in sheet_url:
        sheet_id = sheet_url.split("/d/")[1].split("/")[0]
        spreadsheet = gc.open_by_key(sheet_id)
    else:
        spreadsheet = gc.open(SHEET_NAME)
    sheet = spreadsheet.sheet1

    # 確認第一行是標題列，如果是空的就先建立標題
    existing = sheet.get_all_values()
    if not existing or not existing[0] or existing[0][0] != "日期":
        sheet.insert_row(
            ["日期", "趨勢主題", "文案內容", "圖片連結", "Hashtags", "排程時間", "狀態", "發文結果"],
            index=1,
        )

    # 預設排程時間為下週一中午 12:00（台灣時間）
    next_monday = datetime.now() + timedelta(days=(7 - datetime.now().weekday()))
    scheduled_time = next_monday.replace(hour=12, minute=0, second=0).strftime("%Y-%m-%d %H:%M")

    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d"),   # 日期
        content.get("topic", ""),               # 趨勢主題
        content.get("caption", ""),             # 文案內容
        content.get("image_url", ""),              # 圖片連結
        ", ".join(content.get("hashtags", [])), # Hashtags
        scheduled_time,                         # 排程時間
        "pending",                              # 狀態
        "",                                     # 發文結果
    ])
    print(f"✅ 已寫入 Google Sheet：{content.get('topic', '')}")


# ── Gmail 通知 ───────────────────────────────────────────────
def send_notification(subject: str, body: str) -> None:
    """透過 Gmail 發送通知信。"""
    gmail_address = GMAIL_ADDRESS
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_address or not app_password:
        print("⚠️  未設定 GMAIL_ADDRESS 或 GMAIL_APP_PASSWORD，跳過通知。")
        return

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = gmail_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.send_message(msg)

    print(f"✅ 通知信已寄出：{subject}")


# ── 主流程 ───────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"開始執行 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. 爬取時尚新聞
    print("\n📰 步驟 1：爬取時尚新聞...")
    articles = parse_feeds()
    articles_summary = build_articles_summary(articles)

    if not articles:
        print("⚠️  本週未抓到任何文章，流程終止。")
        return

    # 2. Claude 生成文案（三步驟：3 個切入點 → AI 選最好的＋口語化 → 輕量校對）
    print("\n✍️  步驟 2a：呼叫 Claude 生成 3 個不同切入點...")
    drafts_data = generate_three_drafts(articles_summary)
    for i, d in enumerate(drafts_data.get("drafts", []), 1):
        print(f"   切入點 {i}：{d.get('angle', '')}")

    print("\n✍️  步驟 2b：AI 選出最自然的版本並口語化改寫...")
    content = select_and_rewrite(drafts_data)
    print(f"   選擇了版本 {content.get('selected_version', '?')}：{content.get('reason', '')}")

    print("\n✍️  步驟 2c：最終輕量校對...")
    client = anthropic.Anthropic()
    content = final_check(client, content)
    print(f"   主題：{content.get('topic', '')}")
    print(f"   文案預覽：{content.get('caption', '')[:100]}...")

    # 3. AI 生成圖片 + 上傳 Google Drive
    print("\n🎨 步驟 3：AI 生成圖片...")
    creds = get_google_creds()
    image_prompt = content.get("image_prompt", "")
    image_url = ""
    if image_prompt:
        try:
            image_bytes = generate_image_gemini(image_prompt)
            filename = f"ig_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            print(f"   圖片已生成（{len(image_bytes):,} bytes），上傳到 Google Drive...")
            image_url = upload_to_drive(creds, image_bytes, filename)
        except Exception as e:
            print(f"⚠️  圖片生成或上傳失敗：{e}")
            print("   將繼續流程，圖片欄位留空。")
    else:
        print("⚠️  沒有 image_prompt，跳過圖片生成。")
    content["image_url"] = image_url

    # 4. 寫入 Google Sheet
    print("\n📊 步驟 4：寫入 Google Sheet...")
    write_to_sheet(creds, content)

    # 5. Gmail 通知
    print("\n📧 步驟 5：寄送審核通知...")
    caption_preview = content.get("caption", "")[:200]
    send_notification(
        subject=f"🔔 本週 IG 內容待審核 — {content.get('topic', '')}",
        body=f"""
        <h2>📋 本週 IG 內容已生成，請前往審核</h2>
        <hr>
        <p><b>趨勢主題：</b>{content.get('topic', '')}</p>
        <p><b>文案預覽：</b><br>{caption_preview}...</p>
        <p><b>AI 繪圖提示詞：</b><br><i>{content.get('image_prompt', '')}</i></p>
        {f'<p><b>圖片預覽：</b><br><a href="{image_url}">點此查看圖片</a></p>' if image_url else '<p><b>圖片：</b>未生成</p>'}
        <hr>
        <p>👉 <a href="{SHEET_URL}">前往 Google Sheet 審核</a></p>
        <p><small>將「狀態」欄改為 <b>approved</b> 即可排入發文。</small></p>
        """,
    )

    print("\n🎉 完成！")


if __name__ == "__main__":
    main()
