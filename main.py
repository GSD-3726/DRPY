import asyncio
import aiohttp
import re
import subprocess
import time
from datetime import datetime

SCORE_THRESHOLD = 80
MAX_PER_CATEGORY = 5
SEM = asyncio.Semaphore(10)

# =============================
# 分类规则
# =============================
CATEGORY_RULES = {
    "央视": ["cctv"],
    "卫视": ["卫视"],
    "电影": ["电影", "movie", "影院"],
    "轮播": ["轮播", "测试"],
    "少儿": ["少儿", "动漫", "kid"],
}

# =============================
# 广告关键词
# =============================
AD_KEYWORDS = [
    "购物", "广告", "promo", "shop", "试看"
]

# =============================
# LOGO 匹配（示例规则）
# =============================
def generate_logo(name):
    name_clean = re.sub(r'\s+', '', name)
    return f"https://logo.clearbit.com/{name_clean}.com"

# =============================
# 分类
# =============================
def classify_channel(name):
    lower = name.lower()
    for category, keywords in CATEGORY_RULES.items():
        for k in keywords:
            if k.lower() in lower:
                return category
    return "其他"

# =============================
# 广告过滤
# =============================
def is_ad_channel(name):
    for k in AD_KEYWORDS:
        if k.lower() in name.lower():
            return True
    return False

# =============================
# 多地区测速（模拟多节点）
# =============================
async def multi_region_speed_test(url):
    regions = ["asia", "eu", "us"]
    delays = []
    for _ in regions:
        try:
            start = time.time()
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as r:
                    if r.status != 200:
                        continue
                    await r.content.read(1024)
            delays.append(time.time() - start)
        except:
            continue

    if not delays:
        return None

    avg_delay = sum(delays) / len(delays)
    return avg_delay

# =============================
# 评分
# =============================
def calculate_score(delay, width, bitrate):
    score = 0

    if delay < 1:
        score += 30
    elif delay < 1.5:
        score += 20

    if width >= 1920:
        score += 30
    elif width >= 1280:
        score += 20

    if bitrate > 4000000:
        score += 20
    elif bitrate > 2000000:
        score += 10

    return score

# =============================
# 解析 m3u
# =============================
async def parse_m3u(url):
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as r:
                if r.status != 200:
                    return []
                text = await r.text()

        lines = text.splitlines()
        for i in range(len(lines)):
            if lines[i].startswith("#EXTINF"):
                name = lines[i]
                stream_url = lines[i+1] if i+1 < len(lines) else ""
                if stream_url.startswith("http"):
                    results.append((name, stream_url))
    except:
        pass
    return results

# =============================
# 测试单个流
# =============================
async def test_stream(name, url):
    async with SEM:
        try:
            if is_ad_channel(name):
                return None

            delay = await multi_region_speed_test(url)
            if delay is None:
                return None

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    text = await r.text()

            ts_match = re.search(r'(http.*?\.ts)', text)
            if not ts_match:
                return None

            ts_url = ts_match.group(1)

            start_speed = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(ts_url) as r:
                    content = await r.read()
            duration = time.time() - start_speed
            bitrate = len(content) / duration

            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width",
                "-of", "csv=p=0",
                url
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None

            width = int(result.stdout.strip())
            score = calculate_score(delay, width, bitrate)

            if score < SCORE_THRESHOLD:
                return None

            category = classify_channel(name)
            logo = generate_logo(name)

            return {
                "category": category,
                "name": name,
                "url": url,
                "score": score,
                "logo": logo
            }

        except:
            return None

# =============================
# 主程序
# =============================
async def main():

    with open("base_sources.txt") as f:
        sources = [x.strip() for x in f if x.strip()]

    all_streams = []

    for source in sources:
        streams = await parse_m3u(source)
        all_streams.extend(streams)

    tasks = [test_stream(name, url) for name, url in all_streams]
    results = await asyncio.gather(*tasks)

    results = [r for r in results if r]

    # 去重相同频道（保留最高分）
    unique_channels = {}
    for r in results:
        name = r["name"]
        if name not in unique_channels or r["score"] > unique_channels[name]["score"]:
            unique_channels[name] = r

    final_list = list(unique_channels.values())

    # 分类排序
    categorized = {}
    for item in final_list:
        categorized.setdefault(item["category"], []).append(item)

    for cat in categorized:
        categorized[cat].sort(key=lambda x: x["score"], reverse=True)
        categorized[cat] = categorized[cat][:MAX_PER_CATEGORY]

    # 写入 m3u
    with open("output.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# 更新时间: {datetime.utcnow()} UTC\n\n")

        for category in ["央视", "卫视", "电影", "轮播", "少儿", "其他"]:
            if category not in categorized:
                continue

            f.write(f"# ===== {category} =====\n")

            for item in categorized[category]:
                f.write(
                    f'#EXTINF:-1 tvg-logo="{item["logo"]}" '
                    f'group-title="{category}",'
                    f'{item["name"]} ({item["score"]})\n'
                )
                f.write(item["url"] + "\n")

            f.write("\n")

asyncio.run(main())
