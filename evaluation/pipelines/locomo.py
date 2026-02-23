"""LoCoMo evaluation pipeline: ingest → query → evaluate (parallel)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta

from evaluation.config import EvalConfig
from evaluation.datasets.locomo_loader import LoCoMoConversation, load_locomo
from evaluation.metrics.bleu import compute_bleu1
from evaluation.metrics.llm_judge import judge_locomo
from evaluation.metrics.token_f1 import compute_f1
from evaluation.pipelines.base import (
    cleanup_user,
    create_judge_llm,
    create_nm,
    load_checkpoint,
    save_checkpoint,
    set_embedding_timestamps,
    set_timestamps,
)
from evaluation.prompts.answer import LOCOMO_ANSWER_SYSTEM, LOCOMO_ANSWER_USER

logger = logging.getLogger(__name__)

# Rate-limit retry settings
_MAX_RETRIES = 5
_BASE_DELAY = 5.0  # seconds


async def _retry_on_rate_limit(coro_fn, *args, **kwargs):
    """Retry an async call with exponential backoff on rate-limit errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(kw in err_str for kw in (
                "429", "rate", "too many", "502", "503", "overloaded",
            ))
            if is_rate_limit and attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Rate limited (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1, _MAX_RETRIES, delay, str(e)[:80],
                )
                await asyncio.sleep(delay)
            else:
                raise


async def run_locomo(cfg: EvalConfig, phase: str | None = None, conv_filter: int | None = None) -> None:
    """Run LoCoMo evaluation (all phases or a specific one)."""
    conversations = load_locomo(cfg.locomo_data_path)
    logger.info("Loaded %d LoCoMo conversations", len(conversations))

    if conv_filter is not None:
        conversations = [c for c in conversations if c.conv_idx == conv_filter]
        logger.info("Filtered to conv %d (%d conversations)", conv_filter, len(conversations))

    logger.info(
        "Concurrency: ingest=%d, query=%d, evaluate=%d",
        cfg.ingest_concurrency, cfg.query_concurrency, cfg.evaluate_concurrency,
    )

    if phase is None or phase == "ingest":
        await _ingest(cfg, conversations)
    if phase is None or phase == "query":
        await _query(cfg, conversations)
    if phase is None or phase == "evaluate":
        await _evaluate(cfg, conv_filter=conv_filter)


# ---------------------------------------------------------------------------
# Phase 1: Ingest (parallel across conversations)
# ---------------------------------------------------------------------------

async def _ingest(cfg: EvalConfig, conversations: list[LoCoMoConversation]) -> None:
    """Ingest conversations in parallel, bounded by ingest_concurrency."""
    # Pre-init DB schema once to avoid concurrent CREATE TABLE races
    nm0 = create_nm(cfg)
    await nm0.init()
    await nm0.close()

    sem = asyncio.Semaphore(cfg.ingest_concurrency)

    async def _ingest_one(conv: LoCoMoConversation) -> None:
        async with sem:
            nm = create_nm(cfg)
            await nm.init()
            try:
                await _ingest_conversation(cfg, nm, conv)
            finally:
                await nm.close()

    tasks = [asyncio.create_task(_ingest_one(c)) for c in conversations]
    await asyncio.gather(*tasks)
    logger.info("Ingest phase complete: %d conversations", len(conversations))


async def _ingest_conversation(
    cfg: EvalConfig, nm, conv: LoCoMoConversation
) -> None:
    """Ingest a single conversation for both speakers."""
    user_a = f"{conv.speaker_a}_{conv.conv_idx}"
    user_b = f"{conv.speaker_b}_{conv.conv_idx}"
    logger.info(
        "Ingesting conv %d: %s, %s (%d sessions)",
        conv.conv_idx, user_a, user_b, len(conv.sessions),
    )

    await cleanup_user(nm, user_a)
    await cleanup_user(nm, user_b)

    base_ts = datetime(2023, 1, 1)

    for sess in conv.sessions:
        ts = sess.timestamp or (base_ts + timedelta(days=sess.session_idx * 7))

        sid_a = f"conv{conv.conv_idx}_a_s{sess.session_idx}"
        msg_meta = {"session_timestamp": ts.isoformat()}
        for msg in sess.messages:
            role_a = "user" if msg.speaker == conv.speaker_a else "assistant"
            content = f"{msg.speaker}: {msg.text}"
            await _retry_on_rate_limit(
                nm.conversations.add_message,
                user_id=user_a, role=role_a, content=content,
                session_id=sid_a, metadata=msg_meta,
            )

        sid_b = f"conv{conv.conv_idx}_b_s{sess.session_idx}"
        for msg in sess.messages:
            role_b = "user" if msg.speaker == conv.speaker_b else "assistant"
            content = f"{msg.speaker}: {msg.text}"
            await _retry_on_rate_limit(
                nm.conversations.add_message,
                user_id=user_b, role=role_b, content=content,
                session_id=sid_b, metadata=msg_meta,
            )

        await set_timestamps(nm, user_a, sid_a, ts)
        await set_timestamps(nm, user_b, sid_b, ts)

    # Reflect: extract memories + generate insights
    # If reflection_interval > 0, reflect runs automatically in background via library.
    # Otherwise fall back to explicit synchronous reflect (unless skip_reflect).
    if not cfg.skip_reflect and cfg.reflection_interval == 0:
        for uid in [user_a, user_b]:
            await _reflect_user(cfg, nm, uid)

    logger.info("Ingested conv %d", conv.conv_idx)


async def _reflect_user(cfg: EvalConfig, nm, user_id: str) -> None:
    """Call reflect() to generate insights from all memories."""
    try:
        result = await _retry_on_rate_limit(
            nm.reflect, user_id, batch_size=cfg.extraction_batch_size,
        )
        logger.info(
            "Reflect[%s]: analyzed=%d insights=%d",
            user_id,
            result.get("analyzed", 0),
            result.get("insights_generated", 0),
        )
    except Exception as e:
        logger.error("Reflect failed for %s: %s", user_id, e)


# ---------------------------------------------------------------------------
# Phase 2: Query (parallel across QA items)
# ---------------------------------------------------------------------------

async def _query(cfg: EvalConfig, conversations: list[LoCoMoConversation]) -> None:
    """Query memories and generate answers, parallel across QA items."""
    nm = create_nm(cfg)
    await nm.init()

    checkpoint_path = os.path.join(cfg.results_dir, "locomo_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed_keys = set(checkpoint["completed"])
    ckpt_lock = asyncio.Lock()
    sem = asyncio.Semaphore(cfg.query_concurrency)

    # Use separate answer LLM if configured
    if cfg.answer_llm_model:
        from neuromemory.providers.openai_llm import OpenAILLM
        answer_llm = OpenAILLM(
            api_key=cfg.answer_llm_api_key or cfg.llm_api_key,
            model=cfg.answer_llm_model,
            base_url=cfg.answer_llm_base_url or cfg.llm_base_url,
        )
        logger.info("Using separate answer LLM: %s", cfg.answer_llm_model)
    else:
        answer_llm = nm._llm

    # Collect pending work items
    pending = []
    for conv in conversations:
        user_a = f"{conv.speaker_a}_{conv.conv_idx}"
        user_b = f"{conv.speaker_b}_{conv.conv_idx}"
        for qa_idx, qa in enumerate(conv.qa_pairs):
            if qa.category == 5:
                continue
            result_key = f"{conv.conv_idx}_{qa_idx}"
            if result_key in completed_keys:
                continue
            pending.append((conv, user_a, user_b, qa_idx, qa, result_key))

    logger.info("Query phase: %d pending, %d already done", len(pending), len(completed_keys))

    async def _query_one(conv, user_a, user_b, qa_idx, qa, result_key):
        async with sem:
            t0 = time.time()

            decay_rate = cfg.decay_rate_days * 86400
            # Recall from both speakers concurrently
            recall_a, recall_b = await asyncio.gather(
                _retry_on_rate_limit(
                    nm.recall, user_a, qa.question,
                    limit=cfg.recall_limit, decay_rate=decay_rate,
                ),
                _retry_on_rate_limit(
                    nm.recall, user_b, qa.question,
                    limit=cfg.recall_limit, decay_rate=decay_rate,
                ),
            )

            memories_a = recall_a.get("merged", [])
            memories_b = recall_b.get("merged", [])
            mem_text_a = "\n".join(
                f"- {m.get('display_content') or m.get('content', '')}" for m in memories_a
            ) or "No memories found."
            mem_text_b = "\n".join(
                f"- {m.get('display_content') or m.get('content', '')}" for m in memories_b
            ) or "No memories found."

            # Collect graph context
            graph_ctx_a = recall_a.get("graph_context", [])
            graph_ctx_b = recall_b.get("graph_context", [])
            all_graph = list(dict.fromkeys(graph_ctx_a + graph_ctx_b))
            graph_section = ""
            if all_graph:
                graph_lines = "\n".join(f"- {t}" for t in all_graph[:20])
                graph_section = f"\n\nKnown relationships:\n{graph_lines}"

            # Collect user profiles
            profile_a = recall_a.get("user_profile", {})
            profile_b = recall_b.get("user_profile", {})
            profile_section = _format_profiles(
                user_a, profile_a, user_b, profile_b,
            )

            memories = _merge_memories(memories_a, memories_b)

            system_content = LOCOMO_ANSWER_SYSTEM.format(
                speaker_1=user_a,
                speaker_2=user_b,
                speaker_1_memories=mem_text_a,
                speaker_2_memories=mem_text_b,
            ) + graph_section + profile_section

            predicted = await _retry_on_rate_limit(
                answer_llm.chat,
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": LOCOMO_ANSWER_USER.format(
                        question=qa.question,
                    )},
                ],
                temperature=0.0, max_tokens=128,
            )

            latency = time.time() - t0

            result = {
                "conv_idx": conv.conv_idx,
                "qa_idx": qa_idx,
                "question": qa.question,
                "gold_answer": qa.answer,
                "predicted": predicted.strip(),
                "category": qa.category,
                "num_memories": len(memories),
                "latency": round(latency, 2),
            }

            async with ckpt_lock:
                checkpoint["results"].append(result)
                checkpoint["completed"].append(result_key)
                completed_keys.add(result_key)
                save_checkpoint(checkpoint_path, checkpoint)

            logger.info(
                "Q[%s] cat=%d latency=%.1fs pred=%s",
                result_key, qa.category, latency,
                predicted.strip()[:60],
            )

    try:
        tasks = [
            asyncio.create_task(_query_one(conv, ua, ub, qi, qa, rk))
            for conv, ua, ub, qi, qa, rk in pending
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await nm.close()

    failed = len(pending) - sum(1 for *_, rk in pending if rk in completed_keys)
    logger.info(
        "Query phase complete: %d results (%d failed)",
        len(checkpoint["results"]), failed,
    )


def _format_profiles(
    user_a: str, profile_a: dict,
    user_b: str, profile_b: dict,
) -> str:
    """Format user profiles as additional context for the answer prompt."""
    lines: list[str] = []
    for user, profile in [(user_a, profile_a), (user_b, profile_b)]:
        if not profile:
            continue
        parts: list[str] = []
        if profile.get("identity"):
            parts.append(f"Identity: {profile['identity']}")
        if profile.get("occupation"):
            parts.append(f"Occupation: {profile['occupation']}")
        if profile.get("interests"):
            items = profile["interests"] if isinstance(profile["interests"], list) else [profile["interests"]]
            parts.append(f"Interests: {', '.join(items)}")
        if profile.get("values"):
            items = profile["values"] if isinstance(profile["values"], list) else [profile["values"]]
            parts.append(f"Values: {', '.join(items)}")
        if profile.get("relationships"):
            items = profile["relationships"] if isinstance(profile["relationships"], list) else [profile["relationships"]]
            parts.append(f"Relationships: {', '.join(items)}")
        if profile.get("personality"):
            items = profile["personality"] if isinstance(profile["personality"], list) else [profile["personality"]]
            parts.append(f"Personality: {', '.join(items)}")
        if parts:
            lines.append(f"{user}: {'; '.join(parts)}")

    if not lines:
        return ""
    return "\n\nUser profiles:\n" + "\n".join(f"- {line}" for line in lines)


def _merge_memories(
    list_a: list[dict], list_b: list[dict]
) -> list[dict]:
    """Merge and deduplicate memories from two users."""
    seen: set[str] = set()
    merged: list[dict] = []
    for m in list_a + list_b:
        content = m.get("content", "")
        if content and content not in seen:
            seen.add(content)
            merged.append(m)
    return merged


# ---------------------------------------------------------------------------
# Phase 3: Evaluate (parallel judge calls)
# ---------------------------------------------------------------------------

async def _evaluate(cfg: EvalConfig, conv_filter: int | None = None) -> None:
    """Compute metrics on query results with parallel judge calls."""
    checkpoint_path = os.path.join(cfg.results_dir, "locomo_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    results = checkpoint.get("results", [])

    if conv_filter is not None:
        results = [r for r in results if r.get("conv_idx") == conv_filter]
        logger.info("Filtered evaluate to conv %d: %d results", conv_filter, len(results))

    if not results:
        logger.error("No query results found. Run query phase first.")
        return

    judge_llm = create_judge_llm(cfg)
    sem = asyncio.Semaphore(cfg.evaluate_concurrency)
    total = len(results)

    scored: list[dict | None] = [None] * total
    progress_count = 0
    progress_lock = asyncio.Lock()

    async def _eval_one(idx: int, r: dict) -> None:
        nonlocal progress_count
        cat = r["category"]
        gold = str(r["gold_answer"])
        pred = str(r["predicted"])

        f1 = compute_f1(pred, gold)
        bleu = compute_bleu1(pred, gold)

        async with sem:
            judge_score = await _retry_on_rate_limit(
                judge_locomo, judge_llm, r["question"], gold, pred,
            )

        scored[idx] = {"cat": cat, "f1": f1, "bleu": bleu, "judge": judge_score}

        async with progress_lock:
            progress_count += 1
            if progress_count % 50 == 0 or progress_count == total:
                logger.info(
                    "Evaluate progress: %d/%d (%.0f%%)",
                    progress_count, total, progress_count / total * 100,
                )

    tasks = [asyncio.create_task(_eval_one(i, r)) for i, r in enumerate(results)]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate — skip any None entries from failed tasks
    category_stats: dict[int, dict] = {}
    for s in scored:
        if s is None:
            continue
        cat = s["cat"]
        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "f1": 0.0, "bleu1": 0.0, "judge": 0.0}
        stats = category_stats[cat]
        stats["count"] += 1
        stats["f1"] += s["f1"]
        stats["bleu1"] += s["bleu"]
        stats["judge"] += s["judge"]

    cat_names = {
        1: "multi-hop",
        2: "temporal",
        3: "open-dom",
        4: "single-hop",
    }
    print("\nLoCoMo Evaluation Results")
    print("=" * 55)
    print(f"{'Category':<20} {'Count':>6} {'F1':>8} {'BLEU-1':>8} {'Judge':>8}")
    print("-" * 55)

    total_count = total_f1 = total_bleu = total_judge = 0
    for cat in sorted(category_stats):
        s = category_stats[cat]
        n = s["count"]
        avg_f1 = s["f1"] / n
        avg_bleu = s["bleu1"] / n
        avg_judge = s["judge"] / n
        label = f"{cat} ({cat_names.get(cat, '?')})"
        print(f"{label:<20} {n:>6} {avg_f1:>8.3f} {avg_bleu:>8.3f} {avg_judge:>8.3f}")
        total_count += n
        total_f1 += s["f1"]
        total_bleu += s["bleu1"]
        total_judge += s["judge"]

    print("-" * 55)
    if total_count:
        print(
            f"{'Overall':<20} {total_count:>6} "
            f"{total_f1/total_count:>8.3f} "
            f"{total_bleu/total_count:>8.3f} "
            f"{total_judge/total_count:>8.3f}"
        )

    output_path = os.path.join(cfg.results_dir, "locomo_results.json")
    final = {
        "total_questions": total_count,
        "overall": {
            "f1": total_f1 / total_count if total_count else 0,
            "bleu1": total_bleu / total_count if total_count else 0,
            "judge": total_judge / total_count if total_count else 0,
        },
        "by_category": {
            str(cat): {
                "count": s["count"],
                "f1": s["f1"] / s["count"],
                "bleu1": s["bleu1"] / s["count"],
                "judge": s["judge"] / s["count"],
            }
            for cat, s in category_stats.items()
        },
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final, f, indent=2)
    print(f"\nResults saved to {output_path}")
