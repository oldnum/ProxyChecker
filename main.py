import asyncio, aiohttp, aiofiles
import os, time, re
import logging

logging.basicConfig(format="%(message)s", level=logging.WARNING)

PROXY_FOLDER = "proxy"
OUTPUT_FILE = "valid_proxies.txt"
MAX_CONCURRENT_TASKS = 50

class ProxyChecker:
    def __init__(self):
        self.total_proxies = 0
        self.success_count = 0
        self.failed_count = 0
        self.start_time = 0
        self.valid_proxies = set()  # Track valid proxies in memory
        self.proxy_pattern = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}$") # Regular expression to check proxy format

    async def load_valid_proxies(self):
        # Load existing valid proxies into memory
        if os.path.exists(OUTPUT_FILE):
            async with aiofiles.open(OUTPUT_FILE, mode="r") as f:
                async for line in f:
                    self.valid_proxies.add(line.strip())

    async def handle_valid_proxy(self, proxy):
        # Append proxy to file if not already seen
        if proxy not in self.valid_proxies:
            async with aiofiles.open(OUTPUT_FILE, mode="a") as f:
                await f.write(proxy + "\n")
            self.valid_proxies.add(proxy)

    async def check_proxy(self, session, proxy, semaphore):
        async with semaphore:
            proxy_string = f"http://{proxy}"
            try:
                async with session.get("https://api.ipify.org/?format=json", proxy=proxy_string, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        ip = result.get("ip")
                        proxy_ip = proxy.split(":")[0]
                        if ip == proxy_ip:
                            self.success_count += 1
                            logging.warning(f"🟢 {proxy}")
                            await self.handle_valid_proxy(proxy)
                            return True
                    self.failed_count += 1
                    logging.warning(f"🔴 {proxy}")
            except:
                self.failed_count += 1
                logging.warning(f"🟡 {proxy}")
            return False

    def print_progress(self):
        os.system("cls || clear")
        elapsed_time = time.time() - self.start_time
        remaining_proxies = self.total_proxies - (self.success_count + self.failed_count)
        avg_time_per_proxy = elapsed_time / max(1, self.success_count + self.failed_count)
        remaining_time = avg_time_per_proxy * remaining_proxies

        logging.warning(
            f"\n🔍 Statistics\n"
            f" ├ Total number of proxies: {self.total_proxies}\n"
            f" ├ Valid proxies in file: {len(self.valid_proxies)}\n"
            f" ├ Successful: {self.success_count}\n"
            f" ├ Unsuccessful: {self.failed_count}\n"
            f" ├ Remaining: {remaining_proxies}\n"
            f" └ Estimated completion time: {remaining_time:.2f} s. -> {remaining_time/60:.2f} m.\n"
        )

    async def process_proxies(self):
        if not os.path.exists(PROXY_FOLDER):
            logging.warning(f"🟣 No folder '{PROXY_FOLDER}'")
            return

        await self.load_valid_proxies()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        tasks = []

        async with aiohttp.ClientSession() as session:
            for file in os.listdir(PROXY_FOLDER):
                if file.endswith(".txt"):
                    file_path = os.path.join(PROXY_FOLDER, file)
                    logging.warning(f"🟣 Processing the file: {file_path}")
                    async with aiofiles.open(file_path, mode="r") as f:
                        async for line in f:
                            proxy = line.strip().replace("http://", "")
                            if proxy and self.proxy_pattern.match(proxy):
                                self.total_proxies += 1
                                tasks.append(self.check_proxy(session, proxy, semaphore))
                            else:
                                logging.warning(f"🟡 {proxy}")

            if not tasks:
                logging.warning("🟣 No proxies found to process")
                return

            self.start_time = time.time()
            for i, task in enumerate(asyncio.as_completed(tasks)):
                await task
                if i % 10 == 0:
                    self.print_progress()

        self.print_progress()
        print("🟢 Proxy verification completed")

if __name__ == "__main__":
    proxy_checker = ProxyChecker()
    asyncio.run(proxy_checker.process_proxies())