"""Re-extract all user messages after clearing embeddings.

Usage:
    python scripts/reextract_eval.py [--concurrency 3] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from evaluation.config import EvalConfig
from evaluation.pipelines.base import create_nm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Rate-limit retry settings
_MAX_RETRIES = 5
_BASE_DELAY = 5.0


async def _retry_on_rate_limit(coro_fn, *args, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_retryable = any(kw in err_str for kw in (
                "429", "rate", "too many", "502", "503", "overloaded",
                "timeout", "timed out", "readtimeout",
            ))
            if is_retryable and attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("Retryable error (attempt %d/%d), retrying in %.0fs: %s",
                               attempt + 1, _MAX_RETRIES, delay, str(e)[:80])
                await asyncio.sleep(delay)
            else:
                raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = EvalConfig()

    # Step 1: Apply migration + clear embeddings
    nm = create_nm(cfg)
    await nm.init()

    from sqlalchemy import text, select, func
    from neuromemory.models.conversation import Conversation
    from neuromemory.models.memory import Embedding
    from neuromemory.services.conversation import ConversationService

    if not args.dry_run:
        # Clear all embeddings
        async with nm._db.session() as session:
            result = await session.execute(text("DELETE FROM embeddings"))
            deleted = result.rowcount
            await session.commit()
        logger.info("Cleared %d embeddings", deleted)

        # Also clear graph if present
        try:
            async with nm._db.session() as session:
                await session.execute(text("DELETE FROM graph_edges"))
                await session.execute(text("DELETE FROM graph_nodes"))
                await session.commit()
            logger.info("Cleared graph data")
        except Exception:
            pass

        # Reset extraction status for all messages
        async with nm._db.session() as session:
            result = await session.execute(
                text("UPDATE conversations SET extraction_status = 'pending', "
                     "extraction_error = NULL, extraction_retries = 0")
            )
            logger.info("Reset extraction_status for %d messages", result.rowcount)
            await session.commit()

    # Step 2: Get all user messages grouped by user
    async with nm._db.session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.role == "user")
            .order_by(Conversation.user_id, Conversation.created_at)
        )
        all_msgs = list(result.scalars().all())

    logger.info("Total user messages to extract: %d", len(all_msgs))

    if args.dry_run:
        # Group by user for summary
        from collections import Counter
        by_user = Counter(m.user_id for m in all_msgs)
        for uid, count in sorted(by_user.items()):
            logger.info("  %s: %d messages", uid, count)
        await nm.close()
        return

    # Step 3: Extract with concurrency control
    sem = asyncio.Semaphore(args.concurrency)
    succeeded = 0
    failed = 0
    total = len(all_msgs)
    start_time = time.time()

    async def extract_one(msg):
        nonlocal succeeded, failed
        async with sem:
            try:
                await _retry_on_rate_limit(
                    nm.conversations._extract_single_message,
                    msg.user_id, msg.session_id, [msg],
                )
                # Mark as done
                async with nm._db.session() as session:
                    conv_svc = ConversationService(session)
                    await conv_svc.mark_messages_extracted([msg.id])
                succeeded += 1
            except Exception as e:
                failed += 1
                logger.warning("Extract failed: msg=%s user=%s error=%s",
                               msg.id, msg.user_id, str(e)[:100])
                # Mark as failed
                try:
                    async with nm._db.session() as session:
                        conv_svc = ConversationService(session)
                        await conv_svc.mark_messages_failed([msg.id], str(e)[:500])
                except Exception:
                    pass

            done = succeeded + failed
            if done % 100 == 0 or done == total:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.1f%%) succeeded=%d failed=%d rate=%.1f/s",
                    done, total, 100 * done / total, succeeded, failed, rate,
                )

    tasks = [asyncio.create_task(extract_one(msg)) for msg in all_msgs]
    await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    logger.info(
        "Done: total=%d succeeded=%d failed=%d elapsed=%.0fs",
        total, succeeded, failed, elapsed,
    )

    # Step 4: Summary of failed messages
    if failed > 0:
        async with nm._db.session() as session:
            conv_svc = ConversationService(session)
            failed_msgs = await conv_svc.get_failed_messages(max_retries=99)
        logger.info("Failed messages by user:")
        from collections import Counter
        by_user = Counter(m.user_id for m in failed_msgs)
        for uid, count in sorted(by_user.items()):
            logger.info("  %s: %d", uid, count)

    await nm.close()


if __name__ == "__main__":
    asyncio.run(main())
