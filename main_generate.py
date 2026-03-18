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


# ── Claude 生成文案 ───────────────────────────────────────────
def generate_content(articles_summary: str) -> dict:
    """呼叫 Claude API，根據本週趨勢文章生成 IG 文案。"""

    # 讀取風格範本
    style_guide = ""
    style_guide_path = os.path.join(os.path.dirname(__file__), "style_guide.txt")
    if os.path.exists(style_guide_path):
        with open(style_guide_path, "r", encoding="utf-8") as f:
            style_guide = f.read().strip()

    style_section = (
        f"\n以下是參考的文案風格範本，請模仿這個語氣與節奏：\n{style_guide}"
        if style_guide
        else ""
    )

    client = anthropic.Anthropic()  # 自動讀取 ANTHROPIC_API_KEY

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=f"""你是一個台灣時尚趨勢 IG 帳號的文案編輯。這個帳號的定位是時尚媒體，不是品牌帳號，不賣衣服、不推銷產品。

【文案結構】（三段，總長約 100-150 字）

第一段（1-2 句）：帶入趨勢的切入點。從以下三種開頭方式中隨機選擇：
  (A) 一句英文短句
  (B) 一個具體的畫面或場景（例如某個城市街頭看到的東西）
  (C) 直接切入觀察，沒有引言

第二段（3-5 句）：說明趨勢是什麼、為什麼值得注意。語氣像在跟朋友聊天，不像在寫報告。描述趨勢來源時要具體——提到城市名、品牌名、秀場名或具體的街拍場景，不要用「歐洲街頭」「日系帳號」這種模糊說法。

第三段（1 句）：收尾。從以下方式中隨機選擇：
  (A) 一個簡短的個人觀察
  (B) 一句很平的陳述，不帶哲理感
  (C) 一個沒有答案的問句
  不要每篇都是金句型收尾。有些收尾就是很普通的一句話，那樣反而自然。

【語氣規則】
- 中英文自然混搭，英文比例約 20-30%，通常用在開頭句或關鍵詞
- 用台灣口語，像是在跟認識的人講話
- 不矯情、不說教、不商業
- 短句為主，不要長串的排比句
- 偶爾一篇可以語氣比較鬆散隨便，像編輯趕稿時寫的，不用每篇都維持同一個質感水準

【用詞口語化規則——非常重要】
AI 很容易寫出「文學壓縮」的單字詞，聽起來像在寫散文。台灣人日常打字會用完整的雙字詞或口語說法。請嚴格遵守以下替換：
- 「色」→「顏色」（例如「這三個色」→「這三個顏色」）
- 「沉」→「沉穩」或「沉靜」（不要單獨用「很沉」來形容視覺）
- 「鬆」→「寬鬆」（例如「給得鬆」→「給得很寬鬆」）
- 「撐」→「撐場面」或「撐起來」（例如「在撐」→「在撐場面」）
- 「壓」→「用」或「放」（例如「壓了大量」→「用了大量」或「放了很多」）
- 「走」當作趨勢動詞時 →「往…方向走」或改寫（不要寫「直接往大一號走」這種壓縮句）
- 「帶」→「帶出」「帶入」要寫完整
- 「落」→「落在」「垂落」要寫完整，不要單獨用「落下來」
通用原則：如果一個字拿掉後句子會變得像詩或像散文標題，就改成日常口語的雙字詞版本。寫完後自查：「這句話唸出來像不像在跟朋友講話？」如果像在朗讀，就要改。

【禁用詞彙與句型——嚴格遵守】
- 「就好」「不用...太多」「慢慢」「其實很簡單」「值得擁有」「快去」「不容錯過」
- 「探索」「邂逅」「獨特」「打造」「賦予」「綻放」
- 「不僅…更…」「無論是…還是…」等排比句式
- 「不是 A，是 B」這種否定再肯定的結構——一篇最多出現一次
- 「反而」——每篇最多出現一次
- 「有一種 _____ 的感覺」——盡量避免
- 「開始 _____ 了」——盡量避免
- 「層次不會很厚重」——直接禁用，永遠不要出現

【Hashtag 規則】
- 8-12 個 hashtag
- 中英文混搭
- 固定標籤：#台灣時尚 #FashionTaiwan（二選一，不要兩個都放）
- 其餘根據該篇主題自然搭配
{style_section}

請以 JSON 格式輸出，只輸出 JSON，不要有其他文字，格式如下：
{{
  "topic": "本週趨勢主題（10字以內）",
  "caption": "完整 IG 文案（含 hashtag，hashtag 放在文案最後）",
  "image_prompt": "英文 AI 繪圖提示詞，描述一張時尚編輯風格的圖片，1080x1350px，4:5 直式",
  "hashtags": ["hashtag1", "hashtag2", "...（8-12個，英中混合）"]
}}""",
        messages=[
            {
                "role": "user",
                "content": (
                    f"以下是本週爬取到的時尚趨勢文章摘要：\n\n{articles_summary}\n\n"
                    "請根據以上資訊，撰寫一篇符合上述風格的 IG 文案。"
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # 有時 Claude 會在 JSON 外包一層 ```json ... ```，這裡處理掉
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


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

    # 2. Claude 生成文案
    print("\n✍️  步驟 2：呼叫 Claude 生成文案...")
    content = generate_content(articles_summary)
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
