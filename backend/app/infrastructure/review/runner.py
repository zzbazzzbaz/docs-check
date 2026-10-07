"""审核运行器：把同步引擎调用挪到线程池，避免阻塞事件循环。

并发上限由 worker 的消费协程数控制，这里不再额外加锁。
"""

import asyncio

from app.infrastructure.review.engine import ReviewOutcome, run_review


class ReviewRunner:
    async def run(self, data: bytes) -> ReviewOutcome:
        return await asyncio.to_thread(run_review, data)
