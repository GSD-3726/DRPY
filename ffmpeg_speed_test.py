import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

# ====================== 配置区域（可根据需要修改） ======================
# 稳定的测试链接
TEST_LINKS = [
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "https://cph-p2p-msl.akamaized.net/hls/live/2000341/test/master.m3u8",
    "https://bitdash-a.akamaihd.net/content/sintel/hls/playlist.m3u8",
    "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
    "https://test-streams.mux.dev/pts_shift/master.m3u8",
    "https://test-streams.mux.dev/mp4_segments/master.m3u8",
    "https://test-streams.mux.dev/audio_only/audio_only.m3u8",
    "https://test-streams.mux.dev/video_only/video_only.m3u8",
    "https://test-streams.mux.dev/ttml/embed.m3u8",
    "https://test-streams.mux.dev/webvtt/embed.m3u8",
]
CONCURRENT_A = 6  # 并发模式 A
CONCURRENT_B = 2  # 并发模式 B
TEST_DURATION = 10  # 单个链接测速时长（秒）
# ========================================================================

def test_single_link(link: str, worker_id: str) -> tuple[bool, float, str]:
    """测试单个链接"""
    start_time = time.time()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rw_timeout", "5000000",
                "-t", str(TEST_DURATION),
                "-i", link,
                "-f", "null",
                "-y",
                "-"
            ],
            timeout=TEST_DURATION + 10,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, time.time() - start_time, worker_id
        else:
            return False, time.time() - start_time, worker_id
    except Exception as e:
        return False, time.time() - start_time, worker_id

def worker_task(queue: Queue, worker_id: str):
    """工作线程任务"""
    while not queue.empty():
        try:
            link = queue.get_nowait()
        except:
            break
        success, elapsed, wid = test_single_link(link, worker_id)
        status = "✅" if success else "❌"
        print(f"  [{wid}] {status} 链接后缀: {link[-25:]} | 耗时: {elapsed:.2f}秒")
        queue.task_done()

def run_concurrent_test(concurrent_num: int, test_name: str) -> float:
    """
    运行一轮并发测试
    返回：总耗时
    """
    print(f"\n{'='*100}")
    print(f"🎬 开始【{test_name}】测试 (并发数: {concurrent_num})")
    print(f"{'='*100}")

    # 创建链接队列
    link_queue = Queue()
    for link in TEST_LINKS:
        link_queue.put(link)

    # 记录开始时间
    start_time = time.time()

    # 启动并发池
    with ThreadPoolExecutor(max_workers=concurrent_num) as executor:
        for i in range(concurrent_num):
            executor.submit(worker_task, link_queue, f"线程{i+1}")

    # 等待完成
    link_queue.join()
    total_elapsed = time.time() - start_time

    print(f"\n🏁 【{test_name}】测试完成！总耗时: {total_elapsed:.2f}秒")
    return total_elapsed

def main():
    print(f"🚀 开始 FFmpeg 并发对比测试！")
    print(f"📊 基础配置：单链接测速={TEST_DURATION}秒，测试链接数={len(TEST_LINKS)}")

    # 1. 运行并发 A 测试
    time_a = run_concurrent_test(CONCURRENT_A, f"并发 {CONCURRENT_A}")

    # 2. 运行并发 B 测试
    time_b = run_concurrent_test(CONCURRENT_B, f"并发 {CONCURRENT_B}")

    # 3. 对比结果
    print(f"\n{'='*100}")
    print(f"📈 最终对比结果")
    print(f"{'='*100}")
    print(f"1. 并发 {CONCURRENT_A}:")
    print(f"   - 10个链接耗时: {time_a:.2f}秒")
    print(f"   - 预估100个链接: {time_a * 10:.2f}秒 (约 {time_a * 10 / 60:.1f}分钟)")
    print(f"\n2. 并发 {CONCURRENT_B}:")
    print(f"   - 10个链接耗时: {time_b:.2f}秒")
    print(f"   - 预估100个链接: {time_b * 10:.2f}秒 (约 {time_b * 10 / 60:.1f}分钟)")
    print(f"\n3. 对比:")
    print(f"   - 并发 {CONCURRENT_A} 比 并发 {CONCURRENT_B} 快 {time_b - time_a:.2f}秒 (10链接)")
    print(f"   - 按比例，100链接预计快 {(time_b - time_a) * 10:.2f}秒 (约 {(time_b - time_a) * 10 / 60:.1f}分钟)")

if __name__ == "__main__":
    main()
