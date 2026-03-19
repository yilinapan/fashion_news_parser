"""
main_publish.py
Cron Job 2：每小時檢查 Google Sheet，將 approved 的內容排程到 Buffer 發文。
"""

import os
import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import gspread
import requests
from google.oauth2.service_account import Credentials

# ── 設定 ────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "IG Content Calendar"

BUFFER_ACCESS_TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN", "")
BUFFER_CHANNEL_ID = os.environ.get("BUFFER_CHANNEL_ID", "69ae403d7be9f8b1713841fa")
BUFFER_ORG_ID = os.environ.get("BUFFER_ORG_ID", "69aa8010a757fd1d03ec4017")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


# ── Google 憑證 ─────────────────────────────────────────────
def get_google_creds() -> Credentials:
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


# ── Gmail 通知（失敗時用） ──────────────────────────────────
def send_notification(subject: str, body: str) -> None:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print(f"⚠️  未設定 Gmail，跳過通知：{subject}")
        return

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ 通知信已寄出：{subject}")


# ── Buffer GraphQL API 排程發文 ─────────────────────────────
BUFFER_GRAPHQL_URL = "https://graph.bufferapp.com/graphql"


def publish_to_buffer(caption: str, image_url: str, scheduled_time: str) -> dict:
    """透過 Buffer GraphQL API 建立排程貼文，回傳 API 回應。"""
    headers = {
        "Authorization": f"Bearer {BUFFER_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # 準備 media 參數（有圖片才附圖）
    media_section = ""
    if image_url:
        media_section = f', media: {{ photo: "{image_url}" }}'

    # 準備排程參數
    schedule_section = ""
    if scheduled_time:
        schedule_section = f', scheduledAt: "{scheduled_time}"'

    # 用 escaped 的方式處理文案中的特殊字元
    escaped_caption = caption.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    query = f'''
    mutation {{
      createIdea(input: {{
        organizationId: "{BUFFER_ORG_ID}",
        content: {{
          title: "IG Post",
          text: "{escaped_caption}"
        }},
        channels: ["{BUFFER_CHANNEL_ID}"]{media_section}{schedule_section}
      }}) {{
        ... on Idea {{
          id
          content {{
            title
            text
          }}
        }}
        ... on CoreError {{
          message
        }}
      }}
    }}
    '''

    resp = requests.post(
        BUFFER_GRAPHQL_URL,
        headers=headers,
        json={"query": query},
        timeout=30,
    )
    result = resp.json()

    # 檢查是否有錯誤
    if "errors" in result:
        error_msgs = [e.get("message", str(e)) for e in result["errors"]]
        raise RuntimeError(f"Buffer API 錯誤：{'; '.join(error_msgs)}")

    data = result.get("data", {}).get("createIdea", {})
    if "message" in data:
        raise RuntimeError(f"Buffer API 錯誤：{data['message']}")

    return result


# ── 主流程：掃描 Sheet → 發文 ───────────────────────────────
def main():
    print("=" * 60)
    print(f"檢查待發文內容 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if not BUFFER_ACCESS_TOKEN or not BUFFER_CHANNEL_ID:
        print("⚠️  未設定 BUFFER_ACCESS_TOKEN 或 BUFFER_CHANNEL_ID，流程終止。")
        return

    creds = get_google_creds()
    gc = gspread.authorize(creds)

    # 開啟 Google Sheet
    sheet_url = os.environ.get("SHEET_URL", "")
    if sheet_url and "/d/" in sheet_url:
        sheet_id = sheet_url.split("/d/")[1].split("/")[0]
        spreadsheet = gc.open_by_key(sheet_id)
    else:
        spreadsheet = gc.open(SHEET_NAME)
    sheet = spreadsheet.sheet1

    rows = sheet.get_all_records()
    approved_count = 0

    for i, row in enumerate(rows, start=2):  # start=2 因為第 1 行是標題
        if row.get("狀態") != "approved":
            continue

        approved_count += 1
        topic = row.get("趨勢主題", "")
        caption = row.get("文案內容", "")
        image_url = row.get("圖片連結", "")
        hashtags = row.get("Hashtags", "")
        scheduled_time = row.get("排程時間", "")

        # 文案 + hashtag 合併（如果 hashtag 沒有已經在文案裡的話）
        full_caption = caption
        if hashtags and hashtags not in caption:
            full_caption = f"{caption}\n\n{hashtags}"

        print(f"\n📤 推送到 Buffer：{topic}")
        try:
            publish_to_buffer(
                caption=full_caption,
                image_url=image_url,
                scheduled_time=scheduled_time,
            )
            sheet.update_cell(i, 7, "published")
            sheet.update_cell(i, 8, "成功排程到 Buffer")
            print(f"   ✅ 成功！排程時間：{scheduled_time}")
        except Exception as e:
            error_msg = str(e)
            sheet.update_cell(i, 8, f"失敗：{error_msg}")
            print(f"   ❌ 失敗：{error_msg}")
            send_notification(
                subject=f"⚠️ Buffer 發文失敗 — {topic}",
                body=f"<p><b>主題：</b>{topic}</p><p><b>錯誤：</b>{error_msg}</p>",
            )

    if approved_count == 0:
        print("\n沒有待發文的內容。")
    else:
        print(f"\n🎉 共處理 {approved_count} 筆內容。")


if __name__ == "__main__":
    main()
