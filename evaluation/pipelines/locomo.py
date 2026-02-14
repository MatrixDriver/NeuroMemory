"""LoCoMo evaluation pipeline: ingest → query → evaluate."""

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


async def run_locomo(cfg: EvalConfig, phase: str | None = None) -> None:
    """Run LoCoMo evaluation (all phases or a specific one)."""
    conversations = load_locomo(cfg.locomo_data_path)
    logger.info("Loaded %d LoCoMo conversations", len(conversations))

    if phase is None or phase == "ingest":
        await _ingest(cfg, conversations)
    if phase is None or phase == "query":
        await _query(cfg, conversations)
    if phase is None or phase == "evaluate":
        await _evaluate(cfg)


async def _ingest(cfg: EvalConfig, conversations: list[LoCoMoConversation]) -> None:
    """Phase 1: Ingest conversation messages and extract memories."""
    nm = create_nm(cfg)
    await nm.init()

    try:
        for conv in conversations:
            await _ingest_conversation(cfg, nm, conv)
    finally:
        await nm.close()


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

    # Clean up previous data
    await cleanup_user(nm, user_a)
    await cleanup_user(nm, user_b)

    # Base timestamp for sessions without explicit dates
    base_ts = datetime(2023, 1, 1)

    for sess in conv.sessions:
        ts = sess.timestamp or (base_ts + timedelta(days=sess.session_idx * 7))

        # Add messages for user_a perspective
        sid_a = f"conv{conv.conv_idx}_a_s{sess.session_idx}"
        for msg in sess.messages:
            role_a = "user" if msg.speaker == conv.speaker_a else "assistant"
            content = f"{msg.speaker}: {msg.text}"
            await nm.conversations.add_message(
                user_id=user_a, role=role_a, content=content,
                session_id=sid_a,
            )

        # Add messages for user_b perspective
        sid_b = f"conv{conv.conv_idx}_b_s{sess.session_idx}"
        for msg in sess.messages:
            role_b = "user" if msg.speaker == conv.speaker_b else "assistant"
            content = f"{msg.speaker}: {msg.text}"
            await nm.conversations.add_message(
                user_id=user_b, role=role_b, content=content,
                session_id=sid_b,
            )

        # Set timestamps to match dataset
        await set_timestamps(nm, user_a, sid_a, ts)
        await set_timestamps(nm, user_b, sid_b, ts)

    # Reflect: extract memories + generate insights, in batches
    for uid in [user_a, user_b]:
        await _reflect_user(cfg, nm, uid)

    logger.info("Ingested conv %d", conv.conv_idx)


async def _reflect_user(cfg: EvalConfig, nm, user_id: str) -> None:
    """Repeatedly call reflect() until all messages are extracted.

    reflect() processes up to `limit` unextracted messages per call,
    so we loop until no more remain.
    """
    batch_size = cfg.extraction_batch_size
    round_idx = 0
    while True:
        try:
            result = await nm.reflect(user_id, limit=batch_size)
        except Exception as e:
            logger.error("Reflect failed for %s: %s", user_id, e)
            break
        processed = result.get("conversations_processed", 0)
        if processed == 0:
            break
        round_idx += 1
        logger.info(
            "Reflect[%s] round %d: processed=%d facts=%d prefs=%d insights=%d",
            user_id, round_idx, processed,
            result.get("facts_added", 0),
            result.get("preferences_updated", 0),
            result.get("insights_generated", 0),
        )


async def _query(cfg: EvalConfig, conversations: list[LoCoMoConversation]) -> None:
    """Phase 2: Query memories and generate answers."""
    nm = create_nm(cfg)
    await nm.init()

    checkpoint_path = os.path.join(cfg.results_dir, "locomo_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed_keys = set(checkpoint["completed"])

    answer_llm = nm._llm

    try:
        for conv in conversations:
            user_a = f"{conv.speaker_a}_{conv.conv_idx}"
            user_b = f"{conv.speaker_b}_{conv.conv_idx}"

            for qa_idx, qa in enumerate(conv.qa_pairs):
                # Skip category 5 (adversarial / unanswerable)
                if qa.category == 5:
                    continue

                result_key = f"{conv.conv_idx}_{qa_idx}"
                if result_key in completed_keys:
                    continue

                for attempt in range(3):
                    try:
                        t0 = time.time()

                        # Recall from both speakers
                        decay_rate = cfg.decay_rate_days * 86400
                        recall_a = await nm.recall(
                            user_a, qa.question, limit=cfg.recall_limit,
                            decay_rate=decay_rate,
                        )
                        recall_b = await nm.recall(
                            user_b, qa.question, limit=cfg.recall_limit,
                            decay_rate=decay_rate,
                        )

                        # Format memories per speaker
                        memories_a = recall_a.get("merged", [])
                        memories_b = recall_b.get("merged", [])
                        mem_text_a = "\n".join(
                            f"- {m.get('content', '')}" for m in memories_a
                        ) or "No memories found."
                        mem_text_b = "\n".join(
                            f"- {m.get('content', '')}" for m in memories_b
                        ) or "No memories found."

                        # Merge for counting
                        memories = _merge_memories(memories_a, memories_b)

                        # Generate answer
                        predicted = await answer_llm.chat([
                            {"role": "system", "content": LOCOMO_ANSWER_SYSTEM.format(
                                speaker_1=user_a,
                                speaker_2=user_b,
                                speaker_1_memories=mem_text_a,
                                speaker_2_memories=mem_text_b,
                            )},
                            {"role": "user", "content": LOCOMO_ANSWER_USER.format(
                                question=qa.question,
                            )},
                        ], temperature=0.0, max_tokens=128)

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
                        checkpoint["results"].append(result)
                        checkpoint["completed"].append(result_key)
                        completed_keys.add(result_key)
                        save_checkpoint(checkpoint_path, checkpoint)

                        logger.info(
                            "Q[%s] cat=%d latency=%.1fs pred=%s",
                            result_key, qa.category, latency,
                            predicted.strip()[:60],
                        )
                        break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(
                                "Q[%s] attempt %d failed: %s, retrying...",
                                result_key, attempt + 1, e,
                            )
                            await asyncio.sleep(5)
                        else:
                            logger.error(
                                "Q[%s] failed after 3 attempts: %s, skipping",
                                result_key, e,
                            )
    finally:
        await nm.close()

    logger.info(
        "Query phase complete: %d results", len(checkpoint["results"]),
    )


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


async def _evaluate(cfg: EvalConfig) -> None:
    """Phase 3: Compute metrics on query results."""
    checkpoint_path = os.path.join(cfg.results_dir, "locomo_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    results = checkpoint.get("results", [])

    if not results:
        logger.error("No query results found. Run query phase first.")
        return

    judge_llm = create_judge_llm(cfg)

    # Compute metrics
    category_stats: dict[int, dict] = {}
    total = len(results)

    for idx, r in enumerate(results):
        cat = r["category"]
        gold = str(r["gold_answer"])
        pred = str(r["predicted"])

        f1 = compute_f1(pred, gold)
        bleu = compute_bleu1(pred, gold)
        judge_score = await judge_locomo(judge_llm, r["question"], gold, pred)

        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "f1": 0.0, "bleu1": 0.0, "judge": 0.0}
        stats = category_stats[cat]
        stats["count"] += 1
        stats["f1"] += f1
        stats["bleu1"] += bleu
        stats["judge"] += judge_score

        if (idx + 1) % 50 == 0 or idx + 1 == total:
            logger.info(
                "Evaluate progress: %d/%d (%.0f%%) last_judge=%.0f",
                idx + 1, total, (idx + 1) / total * 100, judge_score,
            )

    # Print results
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

    # Save final results
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
