# P2 Features Design: Memory Enhancement Suite

Date: 2026-03-02
Status: Implemented (v0.9.5)
Scope: P2-1 (Zettelkasten), P2-2 (Two-stage reflection), P2-3 (Dual timeline), P2-4 (Procedural memory), P2-5 (Prospective memory)

## Design Principles

- All features are **transparent** to SDK users — embedded in existing ingest/recall/digest flow, no new API required
- All metadata stored in existing `metadata_` JSONB field — no schema migration
- LLM cost kept minimal — new LLM calls only where essential

---

## P2-3: Dual Timeline (Event Time vs System Time)

### Problem
Facts only record `created_at` (when extracted). When user says "I went to Beijing last Wednesday", the actual event date is lost.

### Design

**Extraction** (memory_extraction.py):
- Add `event_time` field to LLM extraction prompt (ISO date or null)
- LLM resolves relative time expressions ("last week", "next month") to absolute dates using current date context
- If unresolvable, store null — original text preserved in content
- Stored in `metadata_.event_time`

**Recall** (search.py):
- `scored_search` recency bonus uses `event_time` when available, falls back to `created_at`
- This gives temporally accurate recency ranking

**No schema changes** — all via metadata_ JSONB.

---

## P2-5: Prospective Memory

### Problem
Future intentions ("plan to take AWS cert next year") are extracted but never expire. After the target date passes, they remain as current facts.

### Design

**Extraction** (memory_extraction.py):
- Already extracts `temporality=prospective` — no change needed
- `event_time` from P2-3 captures the target date (e.g., "next year" → 2027-01-01)

**Recall** (search.py):
- Prospective facts with `event_time` in the past → apply 0.5x score penalty
- Still retrievable but ranked lower

**Digest** (reflection.py):
- During reflection, scan prospective facts with expired `event_time`
- Auto-update `temporality` from `prospective` to `historical`
- This is a lightweight check, no extra LLM call

---

## P2-4: Procedural Memory

### Problem
System captures behavioral patterns ("active at night") but not operational workflows ("always draws architecture diagram before coding").

### Design

**Extraction** (memory_extraction.py):
- Enhance LLM prompt to recognize multi-step workflows
- When detected, extract as fact with `category=workflow`
- Content format: "Step1 → Step2 → Step3"
- Store `metadata_.procedure_steps: ["Step1", "Step2", "Step3"]` for structured access

**Reflection** (reflection.py):
- When LLM notices repeated similar workflows across conversations, consolidate into behavior trait with `behavior_kind=procedural`
- Already supported by existing trait engine — no changes needed

**Recall** (search.py):
- No special handling — procedural facts participate in normal vector search
- Natural matching through content similarity

**Minimal change** — primarily extraction prompt enhancement + structured metadata storage.

---

## P2-1: Zettelkasten (Memory Inter-linking)

### Problem
Memories are flat and isolated. "Works at Google" and "leads Search team" are stored independently with no explicit link.

### Design

**Link creation** (reflection.py, during digest):
- Reflection prompt already receives new memories in batch
- Additionally load top-K high-importance existing memories as link candidates
- LLM output adds `links: [{source_id, target_id, relation}]`
- Relations are short descriptions: "elaborates", "contradicts", "same topic", "causal"
- Stored in `metadata_.related_memories: [{id, relation}]` on both sides (bidirectional)

**Why not graph storage**:
- Graph stores entity-level relations (person→company)
- Memory links are content-level (fact↔fact)
- Mixing them complicates graph queries
- metadata_ JSONB is lightweight enough

**Recall enhancement** (search.py):
- After initial search results, check `related_memories` on each hit
- Pull linked memories not already in results, apply +0.03 bonus
- Depth limit: 1 hop only
- Max 3 additional linked memories per recall

**LLM context for linking**:
- New memories (post-watermark) + top-K existing memories by importance/access_count
- LLM identifies semantic relationships between them

---

## P2-2: Two-Stage Reflection

### Problem
Current reflection feeds memories directly to LLM for trait inference. LLM may draw conclusions from limited recent context without checking historical evidence.

### Design

**When to use two-stage**:
- Only for "important" reflections: importance accumulated >= 30 or explicit `reflect(force=True)`
- Regular reflections (time-interval, first-time) stay single-stage

**Stage 1 — Question generation**:
- LLM receives new memory summaries
- Outputs 3-5 key questions about the user
- Example: "Has the user's tech stack preference changed?", "What is their current work focus?"
- Lightweight prompt, short output

**Stage 2 — Evidence-based inference**:
- Each question → `search.scored_search()` to retrieve relevant historical memories
- Questions + retrieved evidence + new memories → LLM generates trait conclusions
- Reuses existing trait inference prompt structure

**Implementation**:
- New `_two_stage_reflect()` private method in `ReflectionService`
- Called when trigger_type indicates high importance
- Stage 1 is a separate, small LLM call
- Stage 2 reuses existing `_call_reflection_llm()` with enriched context

**Cost control**:
- Stage 1 output is short (few questions) — low token cost
- Evidence retrieval uses existing vector search — no LLM cost
- Total: 2 LLM calls, but only on important reflections

---

## Files Changed Summary

| File | P2-1 | P2-2 | P2-3 | P2-4 | P2-5 |
|------|------|------|------|------|------|
| services/memory_extraction.py | | | X | X | |
| services/search.py | X | | X | | X |
| services/reflection.py | X | X | | | X |

---

## Testing Strategy

- Unit tests per feature with MockLLM/MockEmbedding
- Integration tests for cross-feature interactions (e.g., prospective fact + dual timeline)
- No new external dependencies
