"""
generate_samples.py
快速生成 10 篇風格測試貼文，用於討論和調整文案方向。
不需要爬蟲，直接模擬 10 個不同的 SS26 趨勢主題。
執行方式：python generate_samples.py
結果存成 sample_posts.txt
"""

import os
import json
import anthropic
from datetime import datetime

# 10 個不同方向的趨勢主題，確保多樣性
TREND_TOPICS = [
    "大地色系回歸：米白、焦糖、深棕成為 SS26 主色調，寬鬆版型為主",
    "Quiet Luxury：低調奢華，去掉 logo，用剪裁和面料說話",
    "Sheer 透明感：薄紗、蕾絲疊穿，若隱若現的輕盈穿搭",
    "Oversized Tailoring：男裝版型女穿，西裝外套加寬褲是這季最強搭配",
    "日系街頭：原宿風格演化，層次感和不對稱剪裁",
    "Monochrome 全身同色：從頭到腳同一個色系，簡單但衝擊力強",
    "Utility / Cargo：機能感單品回潮，多口袋設計進入日常穿搭",
    "Soft Minimalism：極簡但帶有柔和感，棉麻材質、自然皺褶",
    "Paris Fashion Week SS26 亮點：設計師怎麼重新定義「正裝」",
    "二手 vintage 風潮：vintage 店尋寶文化影響主流品牌設計語言",
]


def load_style_guide() -> str:
    path = os.path.join(os.path.dirname(__file__), "style_guide.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def generate_post(client: anthropic.Anthropic, trend: str, style_guide: str) -> dict:
    style_section = (
        f"\n以下是參考的文案風格範本，請模仿這個語氣與節奏：\n{style_guide}"
        if style_guide else ""
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=f"""你是一個台灣時尚趨勢 IG 帳號的文案編輯。這個帳號定位是時尚媒體，不賣衣服、不推銷產品。

【文案結構】（三段，總長約 100-150 字）
第一段（1-2 句）：用一個畫面或簡短的英文句子帶入趨勢，留白感。
第二段（3-5 句）：說明這個趨勢是什麼、為什麼值得關注，語氣像在聊天。
第三段（1 句）：一個簡短的觀察或感受，像是「顏色對了，什麼都好搭。」——不給建議、不說教。

【語氣規則】
- 中英文自然混搭，英文比例約 20-30%，通常用在開頭句或關鍵詞
- 用台灣口語，例如「層次不會很厚重」
- 不矯情、不說教、不商業
- 短句為主
- 禁用：「就好」「不用...太多」「慢慢」「其實很簡單」「值得擁有」「快去」
{style_section}

請以 JSON 格式輸出，只輸出 JSON：
{{
  "topic": "趨勢主題（10字以內）",
  "caption": "完整文案（含 hashtag，hashtag 放最後）",
  "hashtags": ["hashtag1", "hashtag2"]
}}""",
        messages=[{
            "role": "user",
            "content": f"請根據以下趨勢方向撰寫一篇 IG 文案：\n\n{trend}"
        }]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def main():
    print("開始生成 10 篇測試貼文...\n")
    client = anthropic.Anthropic()
    style_guide = load_style_guide()
    results = []

    for i, trend in enumerate(TREND_TOPICS, 1):
        print(f"  生成第 {i}/10 篇：{trend[:20]}...")
        try:
            post = generate_post(client, trend, style_guide)
            results.append((i, trend, post))
        except Exception as e:
            print(f"  ⚠️  第 {i} 篇失敗：{e}")
            results.append((i, trend, None))

    # 寫入文字檔
    output_path = os.path.join(os.path.dirname(__file__), "sample_posts.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"IG 文案測試樣本 — 生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n\n")

        for i, trend, post in results:
            f.write(f"【第 {i} 篇】{post['topic'] if post else '生成失敗'}\n")
            f.write(f"趨勢方向：{trend}\n")
            f.write("-" * 40 + "\n")
            if post:
                f.write(post["caption"])
            else:
                f.write("（生成失敗）")
            f.write("\n\n" + "=" * 60 + "\n\n")

    print(f"\n完成！結果已存到：sample_posts.txt")


if __name__ == "__main__":
    main()
