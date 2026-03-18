"""
main_generate.py
主程式：每週執行一次
流程：爬取時尚新聞 → Claude 生成文案 → 寫入 Google Sheet → Gmail 通知
"""

import os
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

import anthropic
import gspread
from google.oauth2.service_account import Credentials

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

# ── 建立 Google 憑證 ─────────────────────────────────────────
def get_google_creds() -> Credentials:
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


# ── 共用：解析 JSON helper ────────────────────────────────────
def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


# ── Step 1：生成文案草稿 ──────────────────────────────────────
def generate_content(articles_summary: str) -> dict:
    """呼叫 Claude API，根據本週趨勢文章生成 IG 文案草稿。"""

    style_guide = ""
    style_guide_path = os.path.join(os.path.dirname(__file__), "style_guide.txt")
    if os.path.exists(style_guide_path):
        with open(style_guide_path, "r", encoding="utf-8") as f:
            style_guide = f.read().strip()

    style_section = (
        f"\n以下是一個品牌帳號的文案，只參考它的短句節奏和中英混搭方式：\n{style_guide}"
        if style_guide else ""
    )

    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=f"""你是一個台灣時尚趨勢 IG 帳號的文案編輯，定位是時尚媒體，不賣衣服、不推銷產品。

【文案結構】三段，總長約 100-150 字：

第一段（1-2 句）：切入趨勢。每次用不同的方式進入，例如一句英文、一個具體場景描述、或直接說觀察。

第二段（3-5 句）：說明趨勢是什麼、為什麼值得注意。語氣像在跟朋友聊天。要具體，提到品牌名、城市名、秀場名，不要用「歐洲街頭」這種模糊說法。

第三段（1 句）：收尾。可以是一個平淡的觀察、一句陳述、或一個問句，不需要每次都是金句。

【語氣】
- 中英文混搭，英文約 20-30%，通常在開頭句或關鍵詞
- 台灣口語，自然平淡，像在跟認識的人說話
- 短句為主
- 版型描述用「打得很寬鬆」，台灣說「打版」而不是「給版」
- 單字詞要補完整：「顏色」不說「色」、「寬鬆」不說「鬆」、「沉穩」不說「沉」

【Hashtag】8-12 個，中英混搭，#台灣時尚 或 #FashionTaiwan 擇一放。
{style_section}

請以 JSON 格式輸出，只輸出 JSON：
{{
  "topic": "本週趨勢主題（10字以內）",
  "caption": "完整 IG 文案（含 hashtag，hashtag 放在文案最後）",
  "image_prompt": "英文 AI 繪圖提示詞，描述一張時尚編輯風格的圖片，1080x1350px，4:5 直式",
  "hashtags": ["hashtag1", "hashtag2"]
}}""",
        messages=[{
            "role": "user",
            "content": (
                f"以下是本週爬取到的時尚趨勢文章摘要：\n\n{articles_summary}\n\n"
                "請根據以上資訊，撰寫一篇符合上述風格的 IG 文案。"
            ),
        }],
    )

    return _parse_json(message.content[0].text)


# ── Step 2：校對修正 ──────────────────────────────────────────
def revise_caption(client: anthropic.Anthropic, content: dict) -> dict:
    """針對草稿做定點修正，專門處理最頑固的幾個 AI 句式問題。"""

    caption = content.get("caption", "")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system="""你是文案校對，負責找出並修正 IG 貼文裡的特定問題。只改有問題的地方，其他句子不動，語意保持不變。

依序檢查並修正以下六項：

1. 破折號（——）→ 改成逗號或句號，視語意決定

2. 「不是A，是B」「A而是B」「不是A而是B」「比較像A不像B」「還是A只是B」這類否定再肯定句型
   → 直接說B就好，刪掉前面否定A的部分
   例：「不是刻意露，是那種剛好透出來的感覺」→「就是那種剛好透出來的感覺」

3. 「在＋單字動詞」（在走、在退、在跟、在管、在撐、在做）
   → 補完整或換說法
   例：「慢慢在退」→「慢慢退流行了」；「更多人在做的是」→「更多人選擇的是」

4. 「版型給得」→「版型打得」

5. 「台灣這邊」→「台灣」

6. 說教語氣（例如「穿的人比以前更清楚自己在做什麼選擇」、「別再收著等特殊場合了」）
   → 刪掉或改成平述句

回傳完整 JSON，只改 caption 欄位，其他欄位原封不動。""",
        messages=[{
            "role": "user",
            "content": f"請校對以下 IG 文案：\n\n{json.dumps(content, ensure_ascii=False, indent=2)}"
        }],
    )

    revised = _parse_json(message.content[0].text)
    # 保留原始非 caption 欄位，只更新 caption
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
        "",                                     # 圖片連結（階段二填入）
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

    # 2. Claude 生成文案（兩步驟：生成草稿 → 校對修正）
    print("\n✍️  步驟 2：呼叫 Claude 生成文案...")
    client = anthropic.Anthropic()
    content = generate_content(articles_summary)
    print("   草稿完成，進行校對修正...")
    content = revise_caption(client, content)
    print(f"   主題：{content.get('topic', '')}")
    print(f"   文案預覽：{content.get('caption', '')[:100]}...")

    # 3. 寫入 Google Sheet
    print("\n📊 步驟 3：寫入 Google Sheet...")
    creds = get_google_creds()
    write_to_sheet(creds, content)

    # 4. Gmail 通知
    print("\n📧 步驟 4：寄送審核通知...")
    caption_preview = content.get("caption", "")[:200]
    send_notification(
        subject=f"🔔 本週 IG 內容待審核 — {content.get('topic', '')}",
        body=f"""
        <h2>📋 本週 IG 內容已生成，請前往審核</h2>
        <hr>
        <p><b>趨勢主題：</b>{content.get('topic', '')}</p>
        <p><b>文案預覽：</b><br>{caption_preview}...</p>
        <p><b>AI 繪圖提示詞：</b><br><i>{content.get('image_prompt', '')}</i></p>
        <hr>
        <p>👉 <a href="{SHEET_URL}">前往 Google Sheet 審核</a></p>
        <p><small>將「狀態」欄改為 <b>approved</b> 即可排入發文。</small></p>
        """,
    )

    print("\n🎉 完成！")


if __name__ == "__main__":
    main()
