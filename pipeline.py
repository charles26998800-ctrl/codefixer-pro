#!/usr/bin/env python3
"""
CodeFixer Pro — 全自動化內容生成與發布引擎
每天自動執行：爬取高痛點問題 → AI 生成雙語文章 → 轉換為 HTML → 推送到 GitHub
"""

import os
import json
import time
import datetime
import requests
from bs4 import BeautifulSoup

# ============================================================
# 設定區（唯一需要填入的地方）
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# 使用 gemini-1.5-flash（免費額度最充足的模型）
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# ============================================================
# 高價值主題選題庫（AI 策展的「黃金問題資料庫」）
# ============================================================
CURATED_TOPICS = [
    {
        "query": "docker+overlay2",
        "tag": "docker",
        "label": "Docker",
        "tag_class": "tag-docker"
    },
    {
        "query": "python+asyncio",
        "tag": "python",
        "label": "Python",
        "tag_class": "tag-python"
    },
    {
        "query": "next.js+cache",
        "tag": "next.js",
        "label": "Next.js",
        "tag_class": "tag-nextjs"
    },
    {
        "query": "pytorch+cuda+out+of+memory",
        "tag": "pytorch",
        "label": "AI / PyTorch",
        "tag_class": "tag-ai"
    },
    {
        "query": "kubernetes+crashloopbackoff",
        "tag": "kubernetes",
        "label": "Kubernetes",
        "tag_class": "tag-docker"
    },
    {
        "query": "react+useEffect+infinite+loop",
        "tag": "reactjs",
        "label": "React",
        "tag_class": "tag-nextjs"
    },
    {
        "query": "git+merge+conflict",
        "tag": "git",
        "label": "Git",
        "tag_class": "tag-python"
    },
]

# ============================================================
# 第一模組：智能選題引擎（使用 StackExchange 官方 API）
# 官方 API 不會被封鎖，且提供更精準的排序與篩選
# ============================================================
def scrape_top_question(topic):
    """使用 StackExchange 官方 API 抓取高分、高瀏覽量的問題。"""
    tag = topic["tag"]
    print(f"  🔍 正在搜尋主題: {topic['label']} (tag: {tag})")

    # 官方 API：按投票數排序，抓取最有價值的問題
    # 加入 answers=1 確保問題已有解答，body 取得問題內文
    url = (
        f"https://api.stackexchange.com/2.3/questions"
        f"?order=desc&sort=votes&tagged={tag}"
        f"&site=stackoverflow&pagesize=20"
        f"&filter=withbody"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "items" not in data or not data["items"]:
            print(f"  ⚠️  {topic['label']} API 沒有回傳資料，跳過。")
            return None

        # 從結果中篩選出帶有「錯誤感」的問題
        keywords = ["error", "fail", "issue", "exception", "not work",
                    "crash", "broken", "wrong", "undefined", "cannot",
                    "can't", "doesn't", "won't", "warning", "fix"]

        for item in data["items"]:
            title = item.get("title", "")
            # 取問題摘要（移除 HTML 標籤）
            body_html = item.get("body", "")
            import re
            body_text = re.sub(r"<[^>]+>", " ", body_html)
            body_text = re.sub(r"\s+", " ", body_text).strip()
            excerpt = body_text[:300]

            link = item.get("link", "")
            votes = str(item.get("score", 0))
            answer_count = item.get("answer_count", 0)

            # 篩選：有解答 + 帶有問題關鍵字 + 票數 > 50（代表很多人踩過這個坑）
            score = item.get("score", 0)
            if (answer_count > 0 and score > 50 and
                    any(kw in title.lower() for kw in keywords)):
                print(f"  ✅ 找到問題: {title[:60]}... (票數: {votes}, 解答: {answer_count})")
                return {
                    "title": title,
                    "description": excerpt,
                    "link": link,
                    "votes": votes,
                    "topic": topic,
                }

        # 若沒有符合高標準的，退而求其次取第一個有解答的
        for item in data["items"]:
            if item.get("answer_count", 0) > 0:
                title = item.get("title", "")
                body_html = item.get("body", "")
                import re
                body_text = re.sub(r"<[^>]+>", " ", body_html)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                excerpt = body_text[:300]
                link = item.get("link", "")
                votes = str(item.get("score", 0))
                print(f"  ✅ 備選問題: {title[:60]}... (票數: {votes})")
                return {
                    "title": title,
                    "description": excerpt,
                    "link": link,
                    "votes": votes,
                    "topic": topic,
                }

        print(f"  ⚠️  {topic['label']} 未找到合適問題，跳過。")
        return None

    except Exception as e:
        print(f"  ❌ API 錯誤 ({topic['label']}): {e}")
        return None



# ============================================================
# 第二模組：AI 雙語寫手（Gemini 生成英文 + 中文文章）
# ============================================================
def call_gemini(prompt):
    """呼叫 Gemini API 產生文章內容。"""
    if not GEMINI_API_KEY:
        raise ValueError("❌ 缺少 GEMINI_API_KEY！請設定環境變數。")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 2048},
    }
    resp = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def generate_article(question_data, lang="en"):
    """根據爬取的問題，生成指定語言的 SEO 文章。"""
    title = question_data["title"]
    desc = question_data["description"]
    link = question_data["link"]
    topic_label = question_data["topic"]["label"]

    if lang == "en":
        prompt = f"""You are a senior software engineer and experienced technical blogger.
Write a complete, SEO-optimized troubleshooting guide in ENGLISH based on this Stack Overflow question.

Topic: {topic_label}
Question Title: {title}
Question Description: {desc}
Source: {link}

CRITICAL WRITING RULES (follow every single one):
- Write like a REAL engineer sharing their experience, NOT like an AI assistant
- Start with a SHORT personal anecdote (2-3 sentences) about when YOU faced this problem
- Use "I", "my", "me" naturally throughout  
- Include at least one moment of frustration or humor (e.g., "I spent 3 hours on this...")
- Use contractions (don't, can't, it's, you'll) like a native English speaker
- Avoid bullet-point-heavy structure — prefer flowing paragraphs mixed with code blocks
- NEVER use phrases like "In conclusion", "It's worth noting", "As mentioned above"
- End with a casual, friendly closing (1-2 sentences max)

REQUIRED STRUCTURE (in natural prose form):
1. Personal intro paragraph (your story with this bug)
2. "Why does this happen?" section — explain the root cause simply
3. "How I fixed it" — the actual solution with code blocks in markdown format
4. "How to prevent this" — one concrete tip

Return ONLY the article content. Do NOT include frontmatter or metadata.
First line MUST be the article H1 title (starting with #).
"""
    else:  # zh
        prompt = f"""你是一位資深軟體工程師，同時也是有多年經驗的技術部落客。
請根據以下 Stack Overflow 問題，撰寫一篇完整的繁體中文除錯指南。

主題領域: {topic_label}
問題標題: {title}
問題描述: {desc}
來源連結: {link}

寫作規則（每一條都必須遵守）：
- 用「真人工程師分享親身踩坑」的口吻，完全不能像 AI 生成的文章
- 開頭用 2-3 句話描述你「親身遇到這個問題時」的情境（可以有一點情緒，例如「差點崩潰」）
- 自然地使用「我」、「我的」等第一人稱
- 加入至少一個讓讀者產生共鳴的「痛苦時刻」描述
- 語氣要口語、親切、有點幽默，像在跟朋友聊天，不要文謅謅
- 避免過度使用條列式，要有自然的段落敘述
- 絕對不要用「總結來說」、「值得注意的是」、「如上所述」這類 AI 慣用語
- 結尾用輕鬆自然的方式收尾（1-2 句就好）

必須包含的結構（用自然的段落呈現，不要硬套格式）：
1. 個人故事開場（你遇到這個 bug 的情境）
2. 為什麼會發生這個問題（白話解釋根本原因）
3. 我怎麼解決的（實際解決方案，程式碼用 markdown 格式包起來）
4. 怎麼預防再次發生（一個具體的預防建議）

只回傳文章內容，不要包含任何 frontmatter 或 metadata。
第一行必須是文章標題（以 # 開頭）。
"""

    print(f"  ✍️  正在用 Gemini AI 生成{'英文' if lang == 'en' else '中文'}文章...")
    return call_gemini(prompt)


# ============================================================
# 第三模組：HTML 生成器（將 Markdown 文章轉換為網頁）
# ============================================================
def markdown_to_html_basic(md_text):
    """簡單的 Markdown 轉 HTML（適合我們的格式）。"""
    import re
    lines = md_text.split("\n")
    html_lines = []
    in_code = False
    code_lang = ""

    for line in lines:
        # 程式碼區塊
        if line.startswith("```"):
            if not in_code:
                code_lang = line[3:].strip() or "bash"
                html_lines.append(f'<pre><code class="language-{code_lang}">')
                in_code = True
            else:
                html_lines.append("</code></pre>")
                in_code = False
            continue

        if in_code:
            html_lines.append(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            continue

        # 標題
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("---"):
            html_lines.append('<hr class="article-divider" />')
        elif line.strip() == "":
            html_lines.append("")
        else:
            # 處理粗體、行內程式碼
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
            line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', line)
            html_lines.append(f"<p>{line}</p>")

    return "\n".join(html_lines)


def create_article_html(question_data, en_content, zh_content, date_str, slug):
    """生成完整的雙語文章 HTML 頁面。"""
    topic = question_data["topic"]
    tag_label = topic["label"]
    tag_class = topic["tag_class"]

    # 從 markdown 提取標題
    en_title = en_content.split("\n")[0].replace("# ", "").strip()
    zh_title = zh_content.split("\n")[0].replace("# ", "").strip()

    # 內文（移除第一行標題）
    en_body_md = "\n".join(en_content.split("\n")[1:]).strip()
    zh_body_md = "\n".join(zh_content.split("\n")[1:]).strip()

    en_body_html = markdown_to_html_basic(en_body_md)
    zh_body_html = markdown_to_html_basic(zh_body_md)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{en_title} | CodeFixer Pro</title>
  <meta name="description" content="{question_data['description'][:155]}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Inter:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <header class="navbar">
    <div class="container nav-inner">
      <a href="../index.html" class="logo"><span class="logo-icon">⚡</span><span>CodeFixer <em>Pro</em></span></a>
      <nav><a href="../index.html#articles">Articles</a><a href="../index.html#topics">Topics</a></nav>
    </div>
  </header>

  <main class="article-page">
    <a href="../index.html" class="back-link">← Back to Home</a>

    <!-- 語言切換按鈕 -->
    <div class="lang-switcher">
      <button class="lang-btn active" id="btn-en" onclick="switchLang('en')">🇺🇸 English</button>
      <button class="lang-btn" id="btn-zh" onclick="switchLang('zh')">🇹🇼 繁體中文</button>
    </div>

    <!-- 英文版 -->
    <div id="content-en">
      <header class="article-header">
        <div class="card-meta">
          <span class="card-tag {tag_class}">{tag_label}</span>
          <span class="card-date">{date_str}</span>
        </div>
        <h1>{en_title}</h1>
        <p class="summary">Source: <a href="{question_data['link']}" target="_blank" rel="noopener">Stack Overflow ↗</a> · {question_data['votes']} votes</p>
      </header>
      <hr class="article-divider" />
      <div class="article-body">{en_body_html}</div>
    </div>

    <!-- 中文版 -->
    <div id="content-zh" style="display:none">
      <header class="article-header">
        <div class="card-meta">
          <span class="card-tag {tag_class}">{tag_label}</span>
          <span class="card-date">{date_str}</span>
        </div>
        <h1>{zh_title}</h1>
        <p class="summary">來源：<a href="{question_data['link']}" target="_blank" rel="noopener">Stack Overflow ↗</a> · {question_data['votes']} 票</p>
      </header>
      <hr class="article-divider" />
      <div class="article-body">{zh_body_html}</div>
    </div>
  </main>

  <footer class="footer">
    <div class="container footer-inner">
      <span class="logo">⚡ CodeFixer Pro</span>
      <p>© {datetime.date.today().year} CodeFixer Pro. Built for developers worldwide.</p>
    </div>
  </footer>

  <script>
    function switchLang(lang) {{
      document.getElementById('content-en').style.display = lang === 'en' ? 'block' : 'none';
      document.getElementById('content-zh').style.display = lang === 'zh' ? 'block' : 'none';
      document.getElementById('btn-en').classList.toggle('active', lang === 'en');
      document.getElementById('btn-zh').classList.toggle('active', lang === 'zh');
    }}
  </script>
</body>
</html>"""
    return html, en_title, zh_title


# ============================================================
# 第四模組：首頁重建器（自動更新文章列表）
# ============================================================
def rebuild_index(articles_meta, site_dir):
    """根據所有文章的 metadata，重建首頁 HTML。"""
    cards_html = ""
    for i, art in enumerate(articles_meta):
        featured_class = " card-featured" if i == 0 else ""
        featured_badge = '<div class="card-badge">Featured</div>' if i == 0 else ""
        cards_html += f"""
        <article class="card{featured_class}">
          {featured_badge}
          <div class="card-meta">
            <span class="card-tag {art['tag_class']}">{art['tag_label']}</span>
            <span class="card-date">{art['date']}</span>
          </div>
          <h2 class="card-title"><a href="articles/{art['slug']}.html">{art['en_title']}</a></h2>
          <p class="card-excerpt">{art['description'][:180]}...</p>
          <a href="articles/{art['slug']}.html" class="card-cta">Read More →</a>
        </article>"""

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CodeFixer Pro | Technical Troubleshooting Guides</title>
  <meta name="description" content="Your go-to resource for fixing technical errors. Clear, practical guides written by developers, for developers." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Inter:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="navbar">
    <div class="container nav-inner">
      <a href="index.html" class="logo"><span class="logo-icon">⚡</span><span>CodeFixer <em>Pro</em></span></a>
      <nav><a href="#articles">Articles</a><a href="#topics">Topics</a></nav>
    </div>
  </header>

  <section class="hero">
    <div class="container hero-inner">
      <div class="hero-badge">🔥 For Developers</div>
      <h1>Stop Googling.<br/>Start Fixing.</h1>
      <p class="hero-sub">Practical troubleshooting guides for the errors that drive you crazy. Available in English & 繁體中文.</p>
      <div class="hero-stats">
        <div class="stat"><span class="stat-num">{len(articles_meta)}+</span><span class="stat-label">Guides</span></div>
        <div class="stat-divider"></div>
        <div class="stat"><span class="stat-num">2x</span><span class="stat-label">Languages</span></div>
        <div class="stat-divider"></div>
        <div class="stat"><span class="stat-num">Daily</span><span class="stat-label">Updated</span></div>
      </div>
    </div>
    <div class="hero-glow"></div>
  </section>

  <section class="articles" id="articles">
    <div class="container">
      <h2 class="section-title">Latest Articles</h2>
      <div class="article-grid">{cards_html}</div>
    </div>
  </section>

  <footer class="footer">
    <div class="container footer-inner">
      <span class="logo">⚡ CodeFixer Pro</span>
      <p>© {datetime.date.today().year} CodeFixer Pro. Built for developers worldwide.</p>
    </div>
  </footer>
</body>
</html>"""

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print("  📄 首頁已更新。")


# ============================================================
# 主流程：每日自動執行
# ============================================================
def run_daily_pipeline(site_dir="site", max_articles=2):
    """完整的每日執行流程。"""
    today = datetime.date.today().isoformat()
    articles_meta_file = os.path.join(site_dir, "articles_meta.json")

    print(f"\n{'='*55}")
    print(f"  ⚡ CodeFixer Pro 全自動引擎啟動")
    print(f"  📅 日期：{today}")
    print(f"{'='*55}\n")

    # 載入現有文章 metadata
    if os.path.exists(articles_meta_file):
        with open(articles_meta_file, "r", encoding="utf-8") as f:
            articles_meta = json.load(f)
    else:
        articles_meta = []

    new_count = 0
    import random
    topics_today = random.sample(CURATED_TOPICS, min(max_articles, len(CURATED_TOPICS)))

    for topic in topics_today:
        if new_count >= max_articles:
            break

        print(f"\n[主題 {new_count+1}/{max_articles}] {topic['label']}")

        # 爬取問題
        question = scrape_top_question(topic)
        if not question:
            continue

        # 生成文章 slug（URL 用的名稱）
        slug_base = question["title"].lower()
        import re
        slug_base = re.sub(r"[^a-z0-9\s-]", "", slug_base)
        slug_base = re.sub(r"\s+", "-", slug_base.strip())[:50]
        slug = f"{today}-{slug_base}"

        # 確認是否已有同名文章
        if any(a["slug"] == slug for a in articles_meta):
            print(f"  ⏭️  文章已存在，跳過: {slug}")
            continue

        # 生成雙語文章
        try:
            en_content = generate_article(question, lang="en")
            time.sleep(2)  # 避免 API rate limit
            zh_content = generate_article(question, lang="zh")
        except Exception as e:
            print(f"  ❌ AI 生成失敗: {e}")
            continue

        # 建立 HTML 頁面
        article_html, en_title, zh_title = create_article_html(
            question, en_content, zh_content, today, slug
        )
        # 確保 articles 資料夾存在
        articles_dir = os.path.join(site_dir, "articles")
        os.makedirs(articles_dir, exist_ok=True)
        article_path = os.path.join(articles_dir, f"{slug}.html")
        with open(article_path, "w", encoding="utf-8") as f:
            f.write(article_html)
        print(f"  💾 文章已儲存: articles/{slug}.html")

        # 記錄 metadata
        articles_meta.insert(0, {
            "slug": slug,
            "date": today,
            "en_title": en_title,
            "zh_title": zh_title,
            "description": question["description"],
            "tag_label": topic["label"],
            "tag_class": topic["tag_class"],
            "votes": question["votes"],
            "source": question["link"],
        })
        new_count += 1

    # 儲存更新後的 metadata
    with open(articles_meta_file, "w", encoding="utf-8") as f:
        json.dump(articles_meta, f, ensure_ascii=False, indent=2)

    # 重建首頁
    rebuild_index(articles_meta, site_dir)

    print(f"\n{'='*55}")
    print(f"  ✅ 完成！今日新增 {new_count} 篇文章")
    print(f"  📊 網站共有 {len(articles_meta)} 篇文章")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    # 自動偵測執行環境：GitHub Actions 在 repo 根目錄執行，本機在 site/ 子目錄外執行
    import sys
    # 如果當前目錄有 index.html，代表我們已在 site/ 資料夾（本機測試模式）
    # 如果沒有，代表在 repo 根目錄（GitHub Actions 模式）
    if os.path.exists("index.html"):
        site_dir = "."  # 已在 site/ 目錄內
    elif os.path.exists("site/index.html"):
        site_dir = "site"  # 在 repo 根目錄，site/ 在子目錄
    else:
        site_dir = "."  # 預設當前目錄

    run_daily_pipeline(
        site_dir=site_dir,
        max_articles=2  # 每天最多生成幾篇（可調整）
    )
