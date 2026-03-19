"""
generate_samples.py
快速生成測試貼文，用於討論和調整文案方向。
使用與 main_generate.py 相同的新流程：3 個切入點 → AI 選最好的 → 口語化改寫
執行方式：python generate_samples.py
結果存成 sample_posts.txt
"""

import os
import json
import anthropic
from datetime import datetime


# ── 共用函式（從 main_generate 複製，讓這支程式可獨立執行）──────

def _load_file(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), filename)
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

# 測試用趨勢主題（可自由替換）
TREND_TOPICS = [
    "大地色系回歸：米白、焦糖、深棕成為 SS26 主色調，寬鬆版型為主",
    "Quiet Luxury：低調奢華，去掉 logo，用剪裁和面料說話",
    "Sheer 透明感：薄紗、蕾絲疊穿，若隱若現的輕盈穿搭",
]


def generate_and_select(client: anthropic.Anthropic, trend: str) -> dict:
    """對單一趨勢主題執行完整的「3 切入點 → 選稿 → 口語化」流程。"""

    style_guide = _load_file("style_guide.txt")
    fewshot_examples = _load_file("fewshot_examples.txt")

    fewshot_section = ""
    if fewshot_examples:
        fewshot_section = f"\n\n【風格範例——以下是長篇時尚文章，請只分析「語氣、用詞、中英混搭方式」來模仿，不要模仿長度和結構，IG 文案仍要維持 100-150 字短文】\n{fewshot_examples}"

    style_ref = ""
    if style_guide:
        style_ref = f"\n\n【參考節奏】以下品牌帳號的短句節奏和中英混搭可以參考（但你是媒體不是品牌）：\n{style_guide}"

    # 第一輪：生成 3 個切入點
    msg1 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=f"""{PERSONA_PROMPT}

{STYLE_RULES}
{fewshot_section}
{style_ref}

請以 JSON 格式輸出，只輸出 JSON：
{{
  "topic": "趨勢主題（10字以內）",
  "drafts": [
    {{"angle": "切入點簡述", "caption": "完整文案含 hashtag"}},
    {{"angle": "切入點簡述", "caption": "完整文案含 hashtag"}},
    {{"angle": "切入點簡述", "caption": "完整文案含 hashtag"}}
  ]
}}""",
        messages=[{
            "role": "user",
            "content": f"請從 3 個完全不同的切入角度，各寫一篇 IG 文案：\n\n{trend}"
        }]
    )
    drafts_data = _parse_json(msg1.content[0].text)

    # 第二輪：AI 選最好的 + 口語化改寫
    drafts_text = ""
    for i, d in enumerate(drafts_data.get("drafts", []), 1):
        drafts_text += f"\n【版本 {i}】切入點：{d['angle']}\n{d['caption']}\n"

    msg2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=f"""{PERSONA_PROMPT}

從以下 3 個版本中，選出「最不像 AI 寫的、最像真人在 IG 上會發的」，然後把它口語化——想像你在錄語音訊息傳給朋友，重新順一遍。

請以 JSON 格式輸出：
{{
  "selected_version": 1,
  "reason": "一句話說明",
  "topic": "{drafts_data.get('topic', '')}",
  "caption": "口語化改寫後的完整文案含 hashtag",
  "hashtags": ["hashtag 列表"]
}}""",
        messages=[{
            "role": "user",
            "content": f"請選出最好的並口語化改寫：\n{drafts_text}"
        }]
    )
    result = _parse_json(msg2.content[0].text)
    result["all_drafts"] = drafts_data.get("drafts", [])
    return result


def main():
    n = len(TREND_TOPICS)
    print(f"開始生成 {n} 篇測試貼文（新流程：3 切入點 → AI 選稿 → 口語化）...\n")
    client = anthropic.Anthropic()
    results = []

    for i, trend in enumerate(TREND_TOPICS, 1):
        print(f"  [{i}/{n}] {trend[:30]}...")
        try:
            print(f"         生成 3 個切入點中...")
            result = generate_and_select(client, trend)
            print(f"         選擇版本 {result.get('selected_version', '?')}：{result.get('reason', '')}")
            results.append((i, trend, result))
        except Exception as e:
            print(f"  ⚠️  第 {i} 篇失敗：{e}")
            results.append((i, trend, None))

    output_path = os.path.join(os.path.dirname(__file__), "sample_posts.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"IG 文案測試樣本 — 生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"流程：3 個切入點 → AI 自動選稿 → 口語化改寫\n")
        f.write("=" * 60 + "\n\n")

        for i, trend, result in results:
            f.write(f"【第 {i} 篇】{result['topic'] if result else '生成失敗'}\n")
            f.write(f"趨勢方向：{trend}\n")
            if result:
                f.write(f"AI 選擇：版本 {result.get('selected_version', '?')}（{result.get('reason', '')}）\n")
            f.write("-" * 40 + "\n")

            if result:
                # 先列出 3 個草稿供參考
                for j, d in enumerate(result.get("all_drafts", []), 1):
                    f.write(f"\n  〈草稿 {j}〉{d.get('angle', '')}\n")
                    f.write(f"  {d.get('caption', '')[:80]}...\n")

                f.write(f"\n{'─' * 40}\n")
                f.write(f"✅ 最終版本：\n\n")
                f.write(result["caption"])
            else:
                f.write("（生成失敗）")
            f.write("\n\n" + "=" * 60 + "\n\n")

    print(f"\n完成！結果已存到：sample_posts.txt")


if __name__ == "__main__":
    main()
