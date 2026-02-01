import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Set, Optional
import os

import aiofiles
import aiohttp

# Configuration
PROXY_FOLDER = Path("proxies")
OUTPUT_FILE = Path("results/output.txt")
MAX_CONCURRENT_TASKS = 100
CHECK_URL = "https://api.ipify.org/?format=json"
TIMEOUT = 10

# Logging Setup
logging.basicConfig(
    format="%(message)s",
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    proxy: Optional[str] = None,
    timeout: int = TIMEOUT
) -> Optional[dict]:
    # Fetch JSON data from a URL using an optional proxy. 
    proxy_url = f"http://{proxy}" if proxy else None
    try:
        async with session.get(
            url,
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status == 200:
                return await response.json()
    except Exception:
        pass
    return {}

class ProxyChecker:
    def __init__(self):
        self.total_proxies: int = 0
        self.success_count: int = 0
        self.failed_count: int = 0
        self.start_time: float = 0.0
        self.valid_proxies: Set[str] = set()
        self.proxy_pattern = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}$")

    async def load_valid_proxies(self) -> None:
        # Load existing valid proxies from the output file into memory. 
        if OUTPUT_FILE.exists():
            async with aiofiles.open(OUTPUT_FILE, mode="r") as f:
                async for line in f:
                    self.valid_proxies.add(line.strip())

    async def handle_valid_proxy(self, proxy: str) -> None:
        # Save a valid proxy to the output file if it's not already there. 
        if proxy not in self.valid_proxies:
            OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(OUTPUT_FILE, mode="a") as f:
                await f.write(f"{proxy}\n")
            self.valid_proxies.add(proxy)

    async def check_proxy(
        self,
        session: aiohttp.ClientSession,
        proxy: str,
        semaphore: asyncio.Semaphore
    ) -> bool:
        # Check if a single proxy is working by fetching the IP from a public API. 
        async with semaphore:
            result = await fetch_url(session, CHECK_URL, proxy=proxy)
            
            if result:
                ip = result.get("ip")
                proxy_ip = proxy.split(":")[0]
                if ip == proxy_ip:
                    self.success_count += 1
                    logger.warning(f"🟢 {proxy}")
                    await self.handle_valid_proxy(proxy)
                    return True

            self.failed_count += 1
            logger.warning(f"🔴 {proxy}")
            return False

    def print_progress(self) -> None:
        # Print checking progress and statistics. 
        # Clear screen (works for Windows/Unix)        
        os.system("cls" if os.name == "nt" else "clear")

        elapsed_time = time.time() - self.start_time
        checked_count = self.success_count + self.failed_count
        remaining_proxies = self.total_proxies - checked_count
        
        avg_time = elapsed_time / max(1, checked_count)
        remaining_time = avg_time * remaining_proxies

        stats = (
            f"\n{'-'*30}\n"
            f" 🔍 PROXY CHECKER STATISTICS\n"
            f"{'-'*30}\n"
            f" ├ Total Proxies:    {self.total_proxies}\n"
            f" ├ Valid in File:    {len(self.valid_proxies)}\n"
            f" ├ Successful:       {self.success_count}\n"
            f" ├ Unsuccessful:     {self.failed_count}\n"
            f" ├ Remaining:        {remaining_proxies}\n"
            f" └ Est. Completion:  {remaining_time:.1f}s ({remaining_time/60:.1f}m)\n"
            f"{'-'*30}\n"
        )
        logger.warning(stats)

    async def process_proxies(self) -> None:
        # Main loop to process all proxy files in the proxy folder. 
        if not PROXY_FOLDER.exists():
            logger.warning(f"🟣 Folder '{PROXY_FOLDER}' not found.")
            return

        await self.load_valid_proxies()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        tasks = []

        async with aiohttp.ClientSession() as session:
            for file_path in PROXY_FOLDER.glob("*.txt"):
                logger.warning(f"⚪ Processing: {file_path.name}")
                async with aiofiles.open(file_path, mode="r") as f:
                    async for line in f:
                        proxy = line.strip().replace("http://", "")
                        if proxy and self.proxy_pattern.match(proxy):
                            self.total_proxies += 1
                            tasks.append(self.check_proxy(session, proxy, semaphore))

            if not tasks:
                logger.warning("🟣 No valid proxies found to process.")
                return

            self.start_time = time.time()
            for i, task in enumerate(asyncio.as_completed(tasks)):
                await task
                if i % 10 == 0:
                    self.print_progress()

        self.print_progress()
        print("🟢 Proxy verification completed!")

if __name__ == "__main__":
    try:
        checker = ProxyChecker()
        asyncio.run(checker.process_proxies())
    except KeyboardInterrupt:
        print("\n🔴 Stopped by user.")
