"""LongMemEval evaluation pipeline: ingest → query → evaluate (parallel)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

from evaluation.config import EvalConfig
from evaluation.datasets.longmemeval_loader import LongMemEvalQuestion, load_longmemeval
from evaluation.metrics.bleu import compute_bleu1
from evaluation.metrics.llm_judge import judge_longmemeval
from evaluation.metrics.token_f1 import compute_f1
from evaluation.pipelines.base import (
    cleanup_user,
    create_judge_llm,
    create_nm,
    load_checkpoint,
    save_checkpoint,
    set_timestamps,
)
from evaluation.prompts.answer import LONGMEMEVAL_ANSWER_SYSTEM, LONGMEMEVAL_ANSWER_USER

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
            is_retryable = any(kw in err_str for kw in (
                "429", "rate", "too many", "502", "503", "overloaded",
                "timeout", "timed out", "readtimeout",
            ))
            if is_retryable and attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Retryable error (attempt %d/%d), retrying in %.0fs: %s",
                    attempt + 1, _MAX_RETRIES, delay, str(e)[:80],
                )
                await asyncio.sleep(delay)
            else:
                raise


async def run_longmemeval(cfg: EvalConfig, phase: str | None = None, limit: int | None = None) -> None:
    """Run LongMemEval evaluation (all phases or a specific one)."""
    questions = load_longmemeval(cfg.longmemeval_data_path)
    if limit:
        questions = questions[:limit]
        logger.info("Limited to first %d LongMemEval questions", limit)
    logger.info("Loaded %d LongMemEval questions", len(questions))

    if phase is None or phase == "ingest":
        await _ingest(cfg, questions)
    if phase is None or phase == "query":
        await _query(cfg, questions)
    if phase is None or phase == "evaluate":
        await _evaluate(cfg)


# ---------------------------------------------------------------------------
# Phase 1: Ingest (parallel across questions)
# ---------------------------------------------------------------------------

async def _ingest(cfg: EvalConfig, questions: list[LongMemEvalQuestion]) -> None:
    """Ingest haystack sessions in parallel."""
    # Pre-init DB schema once
    nm0 = create_nm(cfg)
    await nm0.init()
    await nm0.close()

    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_ingest_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed = set(checkpoint["completed"])
    ckpt_lock = asyncio.Lock()

    sem = asyncio.Semaphore(cfg.ingest_concurrency)

    async def _ingest_one(q: LongMemEvalQuestion, idx: int) -> None:
        if q.question_id in completed:
            return

        async with sem:
            nm = create_nm(cfg)
            await nm.init()
            user_id = f"lme_{q.question_id}"
            try:
                await cleanup_user(nm, user_id)

                # Batch ingest all sessions
                for sess in q.sessions:
                    session_id = f"{q.question_id}_s{sess.session_idx}"
                    msgs = [
                        {"role": m.role, "content": m.content}
                        for m in sess.messages
                    ]
                    if not msgs:
                        continue
                    
                    # Use add_messages_batch for speed
                    await _retry_on_rate_limit(
                        nm.conversations.add_messages_batch,
                        user_id=user_id, messages=msgs, session_id=session_id,
                    )
                    if sess.timestamp:
                        await set_timestamps(nm, user_id, session_id, sess.timestamp)

                # Reflect: extract memories + generate insights
                # Note: If reflection_interval > 0 in cfg, this might be redundant 
                # but for evaluation we want to ensure everything is processed.
                batch_size = cfg.extraction_batch_size
                round_idx = 0
                while True:
                    result = await _retry_on_rate_limit(nm.reflect, user_id, limit=batch_size)
                    processed = result.get("conversations_processed", 0)
                    if processed == 0:
                        break
                    round_idx += 1
                
                async with ckpt_lock:
                    checkpoint["completed"].append(q.question_id)
                    completed.add(q.question_id)
                    save_checkpoint(checkpoint_path, checkpoint)

                logger.info(
                    "Ingested Q[%d/%d]: %s (%d sessions)",
                    idx + 1, len(questions), q.question_id, len(q.sessions),
                )
            except Exception as e:
                logger.error("Ingest failed for %s: %s", user_id, e)
            finally:
                await nm.close()

    tasks = [asyncio.create_task(_ingest_one(q, i)) for i, q in enumerate(questions)]
    await asyncio.gather(*tasks)
    logger.info("Ingest phase complete: %d questions", len(questions))


# ---------------------------------------------------------------------------
# Phase 2: Query (parallel across questions)
# ---------------------------------------------------------------------------

async def _query(cfg: EvalConfig, questions: list[LongMemEvalQuestion]) -> None:
    """Query memories and generate answers in parallel."""
    nm_base = create_nm(cfg)
    await nm_base.init()

    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed_keys = set(checkpoint["completed"])
    ckpt_lock = asyncio.Lock()

    # Use separate answer LLM if configured
    if cfg.answer_llm_model:
        from neuromem.providers.openai_llm import OpenAILLM
        answer_llm = OpenAILLM(
            api_key=cfg.answer_llm_api_key or cfg.llm_api_key,
            model=cfg.answer_llm_model,
            base_url=cfg.answer_llm_base_url or cfg.llm_base_url,
        )
    else:
        answer_llm = nm_base._llm

    sem = asyncio.Semaphore(cfg.query_concurrency)

    async def _query_one(q: LongMemEvalQuestion, idx: int) -> None:
        if q.question_id in completed_keys:
            return

        async with sem:
            user_id = f"lme_{q.question_id}"
            t0 = time.time()

            # Single recall call to get all context
            recall_result = await _retry_on_rate_limit(
                nm_base.recall, user_id, q.question, limit=cfg.recall_limit,
            )

            merged = recall_result.get("merged", [])
            
            # Format memories for prompt
            facts = [m for m in merged if m.get("memory_type") != "episodic"]
            episodes = [m for m in merged if m.get("memory_type") == "episodic"]
            episodes_sorted = sorted(
                episodes,
                key=lambda m: m.get("extracted_timestamp") or datetime.min.replace(tzinfo=timezone.utc),
            )

            facts_text = "\n".join(f"- {m['content']}" for m in facts) or "None."
            timeline_text = "\n".join(f"- {m['content']}" for m in episodes_sorted) or "None."
            
            # Format graph & profile
            graph_lines = recall_result.get("graph_context", [])[:10]
            graph_text = "\n".join(f"- {g}" for g in graph_lines) or "None."
            
            profile = recall_result.get("user_profile", {})
            profile_lines = [f"{k}: {v}" for k, v in profile.items() if v]
            profile_text = "\n".join(profile_lines) or "None."

            # Track retrieved sessions for Recall@k
            retrieved_sessions = []
            for m in merged:
                meta = m.get("metadata", {}) or {}
                src = meta.get("extracted_from", "") # session_id
                if isinstance(src, str) and "_s" in src:
                    try:
                        s_idx = int(src.split("_s")[-1])
                        if s_idx not in retrieved_sessions:
                            retrieved_sessions.append(s_idx)
                    except (ValueError, IndexError):
                        pass

            # Generate answer
            system_content = LONGMEMEVAL_ANSWER_SYSTEM.format(
                profile=profile_text,
                graph=graph_text,
                facts=facts_text,
                timeline=timeline_text,
            )
            
            predicted = await _retry_on_rate_limit(
                answer_llm.chat,
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": LONGMEMEVAL_ANSWER_USER.format(
                        question=q.question,
                    )},
                ],
                temperature=0.0, max_tokens=256,
            )

            latency = time.time() - t0

            result = {
                "question_id": q.question_id,
                "question": q.question,
                "gold_answer": q.answer,
                "predicted": predicted.strip(),
                "question_type": q.question_type,
                "num_memories": len(merged),
                "retrieved_sessions": retrieved_sessions,
                "answer_sessions": q.answer_sessions,
                "latency": round(latency, 2),
            }

            async with ckpt_lock:
                checkpoint["results"].append(result)
                checkpoint["completed"].append(q.question_id)
                completed_keys.add(q.question_id)
                save_checkpoint(checkpoint_path, checkpoint)

            logger.info(
                "Q[%d/%d] %s latency=%.1fs memories=%d",
                idx + 1, len(questions), q.question_id, latency, len(merged),
            )

    try:
        tasks = [asyncio.create_task(_query_one(q, i)) for i, q in enumerate(questions)]
        await asyncio.gather(*tasks)
    finally:
        await nm_base.close()

    logger.info("Query phase complete: %d results", len(checkpoint["results"]))


def _recall_at_k(
    retrieved_sessions: list[int],
    answer_sessions: list[int],
    k: int = 10,
) -> float:
    """Compute Recall@k: fraction of answer sessions found in top-k retrieved."""
    if not answer_sessions:
        return 1.0
    top_k = set(retrieved_sessions[:k])
    hits = sum(1 for s in answer_sessions if s in top_k)
    return hits / len(answer_sessions)


# ---------------------------------------------------------------------------
# Phase 3: Evaluate (parallel judge calls)
# ---------------------------------------------------------------------------

async def _evaluate(cfg: EvalConfig) -> None:
    """Compute metrics with parallel judge calls."""
    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    results = checkpoint.get("results", [])

    if not results:
        logger.error("No query results found. Run query phase first.")
        return

    judge_llm = create_judge_llm(cfg)
    sem = asyncio.Semaphore(cfg.evaluate_concurrency)
    
    scored: list[dict | None] = [None] * len(results)
    progress_count = 0
    progress_lock = asyncio.Lock()

    async def _eval_one(idx: int, r: dict) -> None:
        nonlocal progress_count
        qtype = r["question_type"]
        gold = str(r["gold_answer"])
        pred = str(r["predicted"])

        f1 = compute_f1(pred, gold)
        bleu = compute_bleu1(pred, gold)
        
        async with sem:
            judge_score = await _retry_on_rate_limit(
                judge_longmemeval, judge_llm, qtype, r["question"], gold, pred,
            )
        
        recall_k = _recall_at_k(
            r.get("retrieved_sessions", []),
            r.get("answer_sessions", []),
        )

        scored[idx] = {
            "qtype": qtype, "f1": f1, "bleu": bleu, 
            "judge": judge_score, "recall_k": recall_k
        }

        async with progress_lock:
            progress_count += 1
            if progress_count % 50 == 0 or progress_count == len(results):
                logger.info("Evaluate progress: %d/%d", progress_count, len(results))

    tasks = [asyncio.create_task(_eval_one(i, r)) for i, r in enumerate(results)]
    await asyncio.gather(*tasks)

    # Aggregate
    type_stats: dict[str, dict] = {}
    total_n = total_f1 = total_bleu = total_judge = total_rk = 0

    for s in scored:
        if s is None: continue
        qtype = s["qtype"]
        if qtype not in type_stats:
            type_stats[qtype] = {
                "count": 0, "f1": 0.0, "bleu1": 0.0, "judge": 0.0, "recall_k": 0.0
            }
        stats = type_stats[qtype]
        stats["count"] += 1
        stats["f1"] += s["f1"]
        stats["bleu1"] += s["bleu"]
        stats["judge"] += s["judge"]
        stats["recall_k"] += s["recall_k"]
        
        total_n += 1
        total_f1 += s["f1"]
        total_bleu += s["bleu"]
        total_judge += s["judge"]
        total_rk += s["recall_k"]

    # Print results
    print("\nLongMemEval Evaluation Results")
    print("=" * 70)
    print(f"{'Type':<20} {'Count':>6} {'F1':>8} {'BLEU-1':>8} {'Judge':>8} {'R@10':>8}")
    print("-" * 70)

    for qtype in sorted(type_stats):
        s = type_stats[qtype]
        n = s["count"]
        print(
            f"{qtype:<20} {n:>6} "
            f"{s['f1']/n:>8.3f} {s['bleu1']/n:>8.3f} "
            f"{s['judge']/n:>8.3f} {s['recall_k']/n:>8.3f}"
        )

    print("-" * 70)
    if total_n:
        print(
            f"{'Overall':<20} {total_n:>6} "
            f"{total_f1/total_n:>8.3f} {total_bleu/total_n:>8.3f} "
            f"{total_judge/total_n:>8.3f} {total_rk/total_n:>8.3f}"
        )

    # Save final results
    output_path = os.path.join(cfg.results_dir, "longmemeval_results.json")
    final = {
        "total_questions": total_n,
        "overall": {
            "f1": total_f1 / total_n if total_n else 0,
            "bleu1": total_bleu / total_n if total_n else 0,
            "judge": total_judge / total_n if total_n else 0,
            "recall_at_10": total_rk / total_n if total_n else 0,
        },
        "by_type": {
            qtype: {
                "count": s["count"],
                "f1": s["f1"] / s["count"],
                "bleu1": s["bleu1"] / s["count"],
                "judge": s["judge"] / s["count"],
                "recall_at_10": s["recall_k"] / s["count"],
            }
            for qtype, s in type_stats.items()
        },
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final, f, indent=2)
    print(f"\nResults saved to {output_path}")
