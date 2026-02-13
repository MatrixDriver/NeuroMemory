.PHONY: locomo longmemeval locomo-ingest locomo-query locomo-evaluate longmemeval-ingest longmemeval-query longmemeval-evaluate

# Full pipelines
locomo:
	python -m evaluation.cli locomo -v

longmemeval:
	python -m evaluation.cli longmemeval -v

# LoCoMo phases
locomo-ingest:
	python -m evaluation.cli locomo --phase ingest -v

locomo-query:
	python -m evaluation.cli locomo --phase query -v

locomo-evaluate:
	python -m evaluation.cli locomo --phase evaluate -v

# LongMemEval phases
longmemeval-ingest:
	python -m evaluation.cli longmemeval --phase ingest -v

longmemeval-query:
	python -m evaluation.cli longmemeval --phase query -v

longmemeval-evaluate:
	python -m evaluation.cli longmemeval --phase evaluate -v
