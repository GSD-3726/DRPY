import requests
import json
import time
import random
import hashlib
import re
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import os

# -------------------------- 核心配置（720P专属） --------------------------
# 线程数（不要过高，避免被风控）
thread_num = 8
# 输出文件路径
m3u_path = 'migu_720p.m3u'
txt_path = 'migu_720p.txt'

# 720P专属：安卓端请求头（完全替换之前的H5头，突破清晰度限制）
headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Origin": "https://m.miguvideo.com",
    "Pragma": "no-cache",
    "Referer": "https://m.miguvideo.com/",
    "User-Agent": "MIGU Video/9.2.1 (Android; SDK 33; 1080x2400)",
    "appCode": "miguvideo_android",
    "appId": "miguvideo",
    "channel": "android",
    "terminalId": "android",
    "appVersion": "9.2.1",
    "playurlVersion": "ZQ-A1-9.2.1-RELEASE"
}

# 频道分类ID（保持不变，适配最新分类）
lives = ['热门', '央视', '卫视', '地方', '体育', '影视', '综艺', '少儿', '新闻', '教育', '熊猫', '纪实']
LIVE = {
    '热门': 'e7716fea6aa1483c80cfc10b7795fcb8',
    '体育': '7538163cdac044398cb292ecf75db4e0',
    '央视': '1ff892f2b5ab4a79be6e25b69d2f5d05',
    '卫视': '0847b3f6c08a4ca28f85ba5701268424',
    '地方': '855e9adc91b04ea18ef3f2dbd43f495b',
    '影视': '10b0d04cb23d4ac5945c4bc77c7ac44e',
    '新闻': 'c584f67ad63f4bc983c31de3a9be977c',
    '教育': 'af72267483d94275995a4498b2799ecd',
    '熊猫': 'e76e56e88fff4c11b0168f55e826445d',
    '综艺': '192a12edfef04b5eb616b878f031f32f',
    '少儿': 'fc2f5b8fd7db43ff88c4243e731ecede',
    '纪实': 'e1165138bdaa44b9a3138d74af6c6673'
}

# M3U标准头部
M3U_HEADER = '#EXTM3U\n'

# 全局存储（去重+排序）
channels_dict = {}
processed_pids = set()

# -------------------------- 工具函数（适配720P规则） --------------------------
def extract_cctv_number(channel_name):
    match = re.search(r'CCTV[-\s]?(\d+)', channel_name)
    if match:
        try:
            return int(match.group(1))
        except:
            return 999
    if 'CCTV' in channel_name:
        if 'CGTN' in channel_name:
            if '法语' in channel_name:
                return 1001
            elif '西班牙语' in channel_name:
                return 1002
            elif '俄语' in channel_name:
                return 1003
            elif '阿拉伯语' in channel_name:
                return 1004
            elif '外语纪录' in channel_name:
                return 1005
            else:
                return 1000
        elif '美洲' in channel_name:
            return 1006
        elif '欧洲' in channel_name:
            return 1007
    return 9999

def extract_panda_number(channel_name):
    zero_match = re.search(r'熊猫0(\d+)', channel_name)
    if zero_match:
        try:
            num = int(zero_match.group(1))
            return (0, num)
        except:
            return (999, 999)
    normal_match = re.search(r'熊猫(\d+)', channel_name)
    if normal_match:
        try:
            num = int(normal_match.group(1))
            return (1, num)
        except:
            return (999, 999)
    return (9999, 9999)

def extract_satellite_first_char(channel_name):
    if not channel_name:
        return 'z'
    first_char = channel_name[0]
    normalized_char = unicodedata.normalize('NFKC', first_char)
    return normalized_char

def get_sort_key(channel_name):
    if 'CCTV' in channel_name:
        cctv_num = extract_cctv_number(channel_name)
        return (0, cctv_num, channel_name)
    if '熊猫' in channel_name:
        panda_num = extract_panda_number(channel_name)
        return (1, panda_num, channel_name)
    if '卫视' in channel_name and 'CCTV' not in channel_name:
        first_char = extract_satellite_first_char(channel_name)
        return (2, first_char, channel_name)
    return (3, channel_name)

def is_cctv_channel(channel_name):
    return 'CCTV' in channel_name or 'CGTN' in channel_name

def is_satellite_channel(channel_name):
    return '卫视' in channel_name and 'CCTV' not in channel_name

def smart_classify_5_categories(channel_name):
    if channel_name in channels_dict:
        return None
    if '熊猫' in channel_name:
        return '🐼熊猫频道'
    if is_cctv_channel(channel_name):
        return '📺央视频道'
    if is_satellite_channel(channel_name):
        return '📡卫视频道'
    lower_name = channel_name.lower()
    entertainment_keywords = ['电影', '影视', '影院', '影迷', '少儿', '卡通', '动漫', '动画',
                              '综艺', '戏曲', '音乐', '秦腔', '嘉佳', '优漫', '新动漫', '经典动画']
    for keyword in entertainment_keywords:
        if keyword in channel_name:
            return '🎬影音娱乐'
    return '📰生活资讯'

def format_date_ymd():
    current_date = datetime.now()
    return f"{current_date.year}{current_date.month:02d}{current_date.day:02d}"

def writefile(path, content, mode='w'):
    with open(path, mode, encoding='utf-8') as f:
        f.write(content)

def md5(text):
    md5_obj = hashlib.md5()
    md5_obj.update(text.encode('utf-8'))
    return md5_obj.hexdigest()

# -------------------------- 核心修改1：新版签名算法（适配720P接口） --------------------------
def getSaltAndSign(pid):
    timestamp = str(int(time.time() * 1000))
    random_num = random.randint(0, 999999)
    salt = f"{random_num:06d}25"
    suffix = "2cac4f2c6c3346a5b34e085725ef7e33migu" + salt[:4]
    app_t = timestamp + pid + "92100000"  # 对应安卓9.2.1版本号
    sign = md5(md5(app_t) + suffix)
    return {
        "salt": salt,
        "sign": sign,
        "timestamp": timestamp
    }

# -------------------------- 核心修改2：720P流地址拼接（适配你抓取的有效链接规则） --------------------------
def get_720p_playurl(base_url, pID):
    """
    基于你抓取的720P链接规则，拼接高清流地址
    强制锁定H.265编码、720P档位、高清节点
    """
    # 基础参数拼接
    puData = base_url.split("&puData=")[1] if "&puData=" in base_url else ""
    keys = "cdabyzwxkl"
    ddCalcu = []
    
    # 新版ddCalcu算法（适配安卓端720P）
    for i in range(0, int(len(puData) / 2)):
        ddCalcu.append(puData[int(len(puData)) - i - 1])
        ddCalcu.append(puData[i])
        if i == 1:
            ddCalcu.append("v")
        if i == 2:
            ddCalcu.append(keys[int(format_date_ymd()[2])])
        if i == 3:
            ddCalcu.append(keys[int(pID[6])])
        if i == 4:
            ddCalcu.append("a")
    
    ddCalcu_str = "".join(ddCalcu)
    
    # 720P专属参数拼接（完全匹配你抓取的有效链接）
    final_url = (
        f"{base_url}"
        f"&ddCalcu={ddCalcu_str}"
        f"&sv=10004&ct=android"
        f"&videocodec=h265&HlsSubType=1&HlsProfileId=1"
        f"&playurlVersion=ZQ-A1-9.2.1-RELEASE"
    )
    return final_url

# -------------------------- 核心修改3：直接请求咪咕原生接口（移除apipost代理，避免降质） --------------------------
def get_content(pid):
    """
    直接请求咪咕安卓端原生接口，不走第三方代理，确保参数不丢失、不被降质
    """
    result = getSaltAndSign(pid)
    # 720P专属rateType：4对应安卓端720P档位（之前的2/3是H5端低清档位）
    rateType = "4"
    
    # 新版playurl接口（v3版本，适配安卓端高清流）
    url = f"https://play.miguvideo.com/playurl/v3/play/playurl"
    params = {
        "sign": result['sign'],
        "rateType": rateType,
        "contId": pid,
        "timestamp": result['timestamp'],
        "salt": result['salt'],
        "clientType": "android",
        "videoCodec": "h265",
        "resolution": "720P"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"接口请求失败，PID:{pid}，错误:{e}")
        return None

# -------------------------- 频道处理逻辑 --------------------------
def append_All_Live(live, data):
    try:
        # 去重
        if data["pID"] in processed_pids:
            return
        processed_pids.add(data["pID"])

        # 获取播放地址
        respData = get_content(data["pID"])
        if not respData or respData.get("code") != "200":
            print(f'频道 [{data["name"]}] 接口返回失败，跳过')
            return
        
        # 提取基础播放地址
        base_url = respData["body"]["urlInfo"]["url"]
        if not base_url:
            print(f'频道 [{data["name"]}] 无有效播放地址，跳过')
            return
        
        # 拼接720P高清地址
        playurl = get_720p_playurl(base_url, data["pID"])

        # 锁定高清节点（匹配你抓取的hlszymgsplive节点，避免跳转到低清节点）
        max_redirect = 5
        redirect_count = 0
        final_playurl = playurl
        while redirect_count < max_redirect:
            try:
                obj = requests.get(final_playurl, allow_redirects=False, timeout=5)
                location = obj.headers.get("Location", "")
                if not location:
                    break
                # 优先保留高清节点
                if location.startswith("http://hlsz"):
                    final_playurl = location
                    break
                final_playurl = location
                redirect_count += 1
                time.sleep(0.1)
            except Exception as e:
                print(f'频道 [{data["name"]}] 重定向校验失败:{e}')
                break

        # 频道名格式化
        ch_name = data["name"]
        if "CCTV" in ch_name:
            ch_name = ch_name.replace("CCTV", "CCTV-")
        if "熊猫" in ch_name:
            ch_name = ch_name.replace("高清", "")

        # 智能分类
        category = smart_classify_5_categories(ch_name)
        if category is None:
            return

        # 排序键
        sort_key = get_sort_key(ch_name)

        # 生成条目
        m3u_item = f'#EXTINF:-1 group-title="{category}",{ch_name}\n{final_playurl}\n'
        txt_item = f"{ch_name},{final_playurl}\n"

        # 存储
        channels_dict[ch_name] = [m3u_item, txt_item, category, sort_key]
        print(f'✅ 频道 [{ch_name}]【{category}】720P流获取成功！')

    except Exception as e:
        print(f'❌ 频道 [{data["name"]}] 获取失败！错误:{e}')

def update(live, url):
    pool = ThreadPoolExecutor(thread_num)
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response_json = response.json()
        dataList = response_json["body"]["dataList"]
        for data in dataList:
            pool.submit(append_All_Live, live, data)
        pool.shutdown(wait=True)
    except Exception as e:
        print(f'分类 [{live}] 列表获取失败！错误:{e}')
        pool.shutdown(wait=False)

# -------------------------- 主函数 --------------------------
def main():
    # 初始化文件
    writefile(m3u_path, M3U_HEADER, 'w')
    writefile(txt_path, "", 'w')

    # 遍历爬取全部分类
    for live in lives:
        print(f"\n==================== 开始爬取 [{live}] 分类 ====================")
        url = f'https://program-sc.miguvideo.com/live/v2/tv-data/{LIVE[live]}'
        update(live, url)

    # 按分类排序
    category_channels = defaultdict(list)
    for ch_name, (m3u_item, txt_item, category, sort_key) in channels_dict.items():
        category_channels[category].append((sort_key, ch_name, m3u_item, txt_item))

    for category in category_channels:
        category_channels[category].sort(key=lambda x: x[0])

    # 按顺序写入文件
    category_order = [
        '📺央视频道',
        '📡卫视频道',
        '🐼熊猫频道',
        '🎬影音娱乐',
        '📰生活资讯'
    ]

    # 写入M3U
    for category in category_order:
        if category in category_channels:
            for sort_key, ch_name, m3u_item, txt_item in category_channels[category]:
                writefile(m3u_path, m3u_item, 'a')

    # 写入TXT
    for category in category_order:
        if category in category_channels and category_channels[category]:
            writefile(txt_path, f"{category},#genre#\n", 'a')
            for sort_key, ch_name, m3u_item, txt_item in category_channels[category]:
                writefile(txt_path, txt_item, 'a')

    # 统计信息
    total_channels = len(channels_dict)
    category_stats = {category: len(channels) for category, channels in category_channels.items()}

    print(f"\n==================== 爬取完成 ====================")
    print(f"📁 720P M3U文件：{m3u_path}")
    print(f"📁 720P TXT文件：{txt_path}")
    print(f"📊 总计成功获取720P频道数：{total_channels}")
    print("\n📋 分类统计：")
    for category in category_order:
        count = category_stats.get(category, 0)
        percentage = (count / total_channels * 100) if total_channels > 0 else 0
        print(f"  {category}: {count} 个 ({percentage:.1f}%)")

if __name__ == "__main__":
    main()
