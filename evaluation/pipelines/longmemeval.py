"""LongMemEval evaluation pipeline: ingest → query → evaluate."""

from __future__ import annotations

import json
import logging
import os
import time

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


async def run_longmemeval(cfg: EvalConfig, phase: str | None = None) -> None:
    """Run LongMemEval evaluation (all phases or a specific one)."""
    questions = load_longmemeval(cfg.longmemeval_data_path)
    logger.info("Loaded %d LongMemEval questions", len(questions))

    if phase is None or phase == "ingest":
        await _ingest(cfg, questions)
    if phase is None or phase == "query":
        await _query(cfg, questions)
    if phase is None or phase == "evaluate":
        await _evaluate(cfg)


async def _ingest(cfg: EvalConfig, questions: list[LongMemEvalQuestion]) -> None:
    """Phase 1: Ingest haystack sessions and extract memories per question."""
    nm = create_nm(cfg)
    await nm.init()

    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_ingest_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed = set(checkpoint["completed"])

    try:
        for q_idx, q in enumerate(questions):
            if q.question_id in completed:
                continue

            user_id = f"lme_{q.question_id}"
            await cleanup_user(nm, user_id)

            # Ingest all haystack sessions
            for sess in q.sessions:
                session_id = f"{q.question_id}_s{sess.session_idx}"
                msgs = [
                    {"role": m.role, "content": m.content}
                    for m in sess.messages
                ]
                if not msgs:
                    continue
                await nm.conversations.add_messages_batch(
                    user_id=user_id, messages=msgs, session_id=session_id,
                )
                if sess.timestamp:
                    await set_timestamps(nm, user_id, session_id, sess.timestamp)

            # Extract memories in batches
            batch_size = cfg.extraction_batch_size
            while True:
                messages = await nm.conversations.get_unextracted_messages(
                    user_id, limit=batch_size,
                )
                if not messages:
                    break
                try:
                    await nm.extract_memories(user_id, messages)
                except Exception as e:
                    logger.error("Extraction failed for %s: %s", user_id, e)
                    break

            checkpoint["completed"].append(q.question_id)
            completed.add(q.question_id)
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "Ingested question %d/%d: %s (%d sessions)",
                q_idx + 1, len(questions), q.question_id, len(q.sessions),
            )
    finally:
        await nm.close()


async def _query(cfg: EvalConfig, questions: list[LongMemEvalQuestion]) -> None:
    """Phase 2: Query memories and generate answers."""
    nm = create_nm(cfg)
    await nm.init()

    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    completed_keys = set(checkpoint["completed"])

    answer_llm = nm._llm

    try:
        for q_idx, q in enumerate(questions):
            if q.question_id in completed_keys:
                continue

            user_id = f"lme_{q.question_id}"
            t0 = time.time()

            recall_result = await nm.recall(
                user_id, q.question, limit=cfg.recall_limit,
            )

            memories = recall_result.get("merged", [])
            memories_text = "\n".join(
                f"- {m.get('content', '')}" for m in memories
            )

            # Track which sessions were retrieved (for Recall@k)
            retrieved_sessions: list[int] = []
            for m in memories:
                meta = m.get("metadata", {}) or {}
                src = meta.get("extracted_from", "")
                if isinstance(src, str) and "_s" in src:
                    try:
                        s_idx = int(src.split("_s")[-1])
                        if s_idx not in retrieved_sessions:
                            retrieved_sessions.append(s_idx)
                    except (ValueError, IndexError):
                        pass

            predicted = await answer_llm.chat([
                {"role": "system", "content": LONGMEMEVAL_ANSWER_SYSTEM.format(
                    memories=memories_text,
                )},
                {"role": "user", "content": LONGMEMEVAL_ANSWER_USER.format(
                    question=q.question,
                )},
            ], temperature=0.0, max_tokens=256)

            latency = time.time() - t0

            result = {
                "question_id": q.question_id,
                "question": q.question,
                "gold_answer": q.answer,
                "predicted": predicted.strip(),
                "question_type": q.question_type,
                "num_memories": len(memories),
                "retrieved_sessions": retrieved_sessions,
                "answer_sessions": q.answer_sessions,
                "latency": round(latency, 2),
            }
            checkpoint["results"].append(result)
            checkpoint["completed"].append(q.question_id)
            completed_keys.add(q.question_id)
            save_checkpoint(checkpoint_path, checkpoint)

            logger.info(
                "Q[%d/%d] %s type=%s latency=%.1fs",
                q_idx + 1, len(questions),
                q.question_id, q.question_type, latency,
            )
    finally:
        await nm.close()

    logger.info(
        "Query phase complete: %d results", len(checkpoint["results"]),
    )


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


async def _evaluate(cfg: EvalConfig) -> None:
    """Phase 3: Compute metrics on query results."""
    checkpoint_path = os.path.join(cfg.results_dir, "longmemeval_query_checkpoint.json")
    checkpoint = load_checkpoint(checkpoint_path)
    results = checkpoint.get("results", [])

    if not results:
        logger.error("No query results found. Run query phase first.")
        return

    judge_llm = create_judge_llm(cfg)

    type_stats: dict[str, dict] = {}

    try:
        from tqdm import tqdm
        iterator = tqdm(results, desc="Evaluating")
    except ImportError:
        iterator = results

    for r in iterator:
        qtype = r["question_type"]
        gold = r["gold_answer"]
        pred = r["predicted"]

        f1 = compute_f1(pred, gold)
        bleu = compute_bleu1(pred, gold)
        judge_score = await judge_longmemeval(
            judge_llm, qtype, r["question"], gold, pred,
        )
        recall_k = _recall_at_k(
            r.get("retrieved_sessions", []),
            r.get("answer_sessions", []),
        )

        if qtype not in type_stats:
            type_stats[qtype] = {
                "count": 0, "f1": 0.0, "bleu1": 0.0,
                "judge": 0.0, "recall_k": 0.0,
            }
        s = type_stats[qtype]
        s["count"] += 1
        s["f1"] += f1
        s["bleu1"] += bleu
        s["judge"] += judge_score
        s["recall_k"] += recall_k

    # Print results
    print("\nLongMemEval Evaluation Results")
    print("=" * 65)
    print(
        f"{'Type':<16} {'Count':>6} {'F1':>8} {'BLEU-1':>8} "
        f"{'Judge':>8} {'R@10':>8}"
    )
    print("-" * 65)

    total_n = total_f1 = total_bleu = total_judge = total_rk = 0
    for qtype in sorted(type_stats):
        s = type_stats[qtype]
        n = s["count"]
        print(
            f"{qtype:<16} {n:>6} "
            f"{s['f1']/n:>8.3f} {s['bleu1']/n:>8.3f} "
            f"{s['judge']/n:>8.3f} {s['recall_k']/n:>8.3f}"
        )
        total_n += n
        total_f1 += s["f1"]
        total_bleu += s["bleu1"]
        total_judge += s["judge"]
        total_rk += s["recall_k"]

    print("-" * 65)
    if total_n:
        print(
            f"{'Overall':<16} {total_n:>6} "
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
