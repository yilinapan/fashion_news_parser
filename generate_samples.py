"""
generate_samples.py
快速生成 3 篇風格測試貼文，用於討論和調整文案方向。
不需要爬蟲，直接用指定的 SS26 趨勢主題測試。
執行方式：python generate_samples.py
結果存成 sample_posts.txt
"""

import os
import json
import anthropic
from datetime import datetime

# 3 個測試用趨勢主題（可自由替換）
TREND_TOPICS = [
    "大地色系回歸：米白、焦糖、深棕成為 SS26 主色調，寬鬆版型為主",
    "Quiet Luxury：低調奢華，去掉 logo，用剪裁和面料說話",
    "Sheer 透明感：薄紗、蕾絲疊穿，若隱若現的輕盈穿搭",
]


def load_style_guide() -> str:
    path = os.path.join(os.path.dirname(__file__), "style_guide.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


# ── Step 1：生成草稿 ──────────────────────────────────────────
def generate_post(client: anthropic.Anthropic, trend: str, style_guide: str) -> dict:
    style_section = (
        f"\n以下是一個品牌帳號的文案，只參考它的短句節奏和中英混搭方式：\n{style_guide}"
        if style_guide else ""
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
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
- 單字詞要補完整：「顏色」不說「色」、「寬鬆」不說「鬆」、「沉穩」不說「沉」、「放鬆/寬鬆」不說「放」（例如「特別放」→「版型特別寬鬆」）
{style_section}

請以 JSON 格式輸出，只輸出 JSON：
{{
  "topic": "趨勢主題（10字以內）",
  "caption": "完整文案（含 hashtag，hashtag 放最後，8-12 個，#台灣時尚 或 #FashionTaiwan 擇一）",
  "hashtags": ["hashtag1", "hashtag2"]
}}""",
        messages=[{
            "role": "user",
            "content": f"請根據以下趨勢方向撰寫一篇 IG 文案：\n\n{trend}"
        }]
    )

    return _parse_json(message.content[0].text)


# ── Step 2：校對修正 ──────────────────────────────────────────
def revise_post(client: anthropic.Anthropic, post: dict) -> dict:
    """針對草稿做定點修正，專門處理最頑固的幾個 AI 句式問題。"""

    caption = post.get("caption", "")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system="""你是文案校對，負責找出並修正 IG 貼文裡的特定問題。只改有問題的地方，其他句子不動，語意保持不變。

依序檢查並修正以下六項：

1. 破折號（——）→ 改成逗號或句號，視語意決定
   例：「走到哪都看得到這個方向——Lemaire 在巴黎」→「走到哪都看得到這個方向，Lemaire 在巴黎」

2. 「不是A，是B」「不是A，就是B」「A而是B」「不是A而是B」「比較像A不像B」「還是A只是B」這類否定再肯定句型
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
            "content": f"請校對以下 IG 文案：\n\n{json.dumps(post, ensure_ascii=False, indent=2)}"
        }],
    )

    revised = _parse_json(message.content[0].text)
    post["caption"] = revised.get("caption", caption)
    return post


def main():
    n = len(TREND_TOPICS)
    print(f"開始生成 {n} 篇測試貼文...\n")
    client = anthropic.Anthropic()
    style_guide = load_style_guide()
    results = []

    for i, trend in enumerate(TREND_TOPICS, 1):
        print(f"  [{i}/{n}] 生成草稿：{trend[:25]}...")
        try:
            post = generate_post(client, trend, style_guide)
            print(f"  [{i}/{n}] 校對修正中...")
            post = revise_post(client, post)
            results.append((i, trend, post))
        except Exception as e:
            print(f"  ⚠️  第 {i} 篇失敗：{e}")
            results.append((i, trend, None))

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
