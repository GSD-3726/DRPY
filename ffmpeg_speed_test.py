import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

# ====================== 配置区域（可根据需要修改） ======================
# 10个测试链接（用公开的视频测试流，你也可以换成自己的链接）
TEST_LINKS = [
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/Sintel.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/SubaruOutbackOnStreetAndDirt.mp4",
    "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
]
CONCURRENT_1 = 6  # 第一个并发数
CONCURRENT_2 = 2  # 第二个并发数
TEST_DURATION = 10  # 单个链接测速时长（秒）
# ========================================================================

def test_single_link(link: str, worker_id: str) -> tuple[bool, float, str]:
    """
    测试单个链接的 FFmpeg 拉流速度
    返回：(是否成功, 耗时, 工作线程ID)
    """
    start_time = time.time()
    try:
        # FFmpeg 命令：拉取 TEST_DURATION 秒的流，不保存文件（仅测速）
        # 参数说明：
        # -t {TEST_DURATION} : 只拉取 10 秒
        # -i {link} : 输入链接
        # -f null - : 输出到空设备（不保存文件）
        # -loglevel error : 只打印错误日志（减少输出）
        subprocess.run(
            ["ffmpeg", "-t", str(TEST_DURATION), "-i", link, "-f", "null", "-", "-loglevel", "error"],
            timeout=TEST_DURATION + 5,  # 超时时间：测速时长+5秒缓冲
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True, time.time() - start_time, worker_id
    except Exception as e:
        return False, time.time() - start_time, worker_id

def worker_task(queue: Queue, worker_id: str):
    """
    工作线程任务：从队列中取链接并测试
    """
    while not queue.empty():
        try:
            link = queue.get_nowait()
        except:
            break
        success, elapsed, wid = test_single_link(link, worker_id)
        status = "✅ 成功" if success else "❌ 失败"
        print(f"[{wid}] 链接 {link[-20:]}... {status}，耗时：{elapsed:.2f}秒")
        queue.task_done()

def main():
    print(f"🚀 开始测试！")
    print(f"📊 配置：并发1={CONCURRENT_1}，并发2={CONCURRENT_2}，单链接测速={TEST_DURATION}秒，总链接数={len(TEST_LINKS)}")
    print("-" * 80)

    # 1. 创建链接队列
    link_queue = Queue()
    for link in TEST_LINKS:
        link_queue.put(link)

    # 2. 记录开始时间
    total_start_time = time.time()

    # 3. 同时启动两个并发池（并发6 + 并发2）
    with ThreadPoolExecutor(max_workers=CONCURRENT_1) as executor1, \
         ThreadPoolExecutor(max_workers=CONCURRENT_2) as executor2:
        
        # 启动并发6的工作线程
        for i in range(CONCURRENT_1):
            executor1.submit(worker_task, link_queue, f"并发6-线程{i+1}")
        
        # 启动并发2的工作线程
        for i in range(CONCURRENT_2):
            executor2.submit(worker_task, link_queue, f"并发2-线程{i+1}")

    # 4. 等待所有链接测试完成
    link_queue.join()

    # 5. 计算总耗时
    total_elapsed = time.time() - total_start_time

    print("-" * 80)
    print(f"🏁 测试完成！")
    print(f"⏱️  总耗时：{total_elapsed:.2f}秒")
    print(f"📌 按此比例预估 100 个链接：{total_elapsed * 10:.2f}秒（仅供参考）")

if __name__ == "__main__":
    main()
