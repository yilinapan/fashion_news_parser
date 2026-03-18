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
        system=f"""你是一個台灣時尚趨勢 IG 帳號的文案編輯。這個帳號的定位是時尚媒體，不是品牌帳號，不賣衣服、不推銷產品。

【文案結構】（三段，總長約 100-150 字）

第一段（1-2 句）：帶入趨勢的切入點。從以下三種開頭方式中隨機選擇，同一批次 10 篇裡至少要用到兩種以上：
  (A) 一句英文短句
  (B) 一個具體的畫面或場景（例如某個城市街頭看到的東西）
  (C) 直接切入觀察，沒有引言

第二段（3-5 句）：說明趨勢是什麼、為什麼值得注意。語氣像在跟朋友聊天，不像在寫報告。描述趨勢來源時要具體——提到城市名、品牌名、秀場名或具體的街拍場景，不要用「歐洲街頭」「日系帳號」這種模糊說法。

第三段（1 句）：收尾。從以下方式中隨機選擇，同一批次裡不要連續兩篇用同一種：
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
- 「不是 A，是 B」這種否定再肯定的結構——一篇最多出現一次，整批 10 篇裡不超過三次
- 「反而」——每篇最多出現一次，整批 10 篇裡不超過四次
- 「有一種 _____ 的感覺」——整批最多出現兩次
- 「開始 _____ 了」——整批最多出現兩次
- 「層次不會很厚重」——直接禁用，永遠不要出現

【批次生成去重規則——最重要】
批次產出多篇文案時，必須在生成完成後自查以下項目：
1. 是否有任何句子片段（超過 6 個字）在多篇中重複出現？如果有，必須改寫
2. 是否有超過三篇使用相同的句式結構（例如都用「A，但 B」轉折）？如果有，替換其中幾篇的寫法
3. 每篇的開頭方式和收尾方式是否有足夠變化？連續兩篇不能用同一種

【Hashtag 規則】
- 8-12 個 hashtag
- 中英文混搭
- 固定標籤：#台灣時尚 #FashionTaiwan（二選一，不要兩個都放）
- 其餘根據該篇主題自然搭配
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
