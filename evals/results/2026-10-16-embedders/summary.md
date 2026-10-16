# Embedder comparison on the three real reports

Same harness, questions, PDFs, chunking and top-20 pool as the 2026-10-15
runs (`evals/README.md`); only `--embed-model` changes, with `--gold any` and
the `default` reranker instruction. The `nomic-embed-text` row is the committed
`2026-10-15-real-{ru,hy,en}.md`. Per-run reports (per-category tables, model
digests, latency) sit next to this file as `<model>-<lang>.md`.

- Models were fixed before the first run: `bge-m3`, `qwen3-embedding:0.6b`,
  `qwen3-embedding:4b`, `nomic-embed-text-v2-moe`.
- Digests: bge-m3 `790764642607`, qwen3-embedding:0.6b `ac6da0dfba84`,
  qwen3-embedding:4b `df5bd2e3c74c`, nomic-embed-text-v2-moe `ff9c2f10ef5e`
  (the per-run reports print `?` for the two without an explicit tag).
- No query or document prefix for any model, which is what the project does
  today. `qwen3-embedding` documents an instruction prefix for queries and
  `nomic-embed-text` a `search_query:` / `search_document:` one, so every row
  is a drop-in swap, not each model at its best.
- `pool` is how many of the 14 questions have the gold chunk in the top 20 by
  cosine, the ceiling for any reranker; `vec` is plain vector order, `rerank`
  is Qwen3-Reranker-4B over the same 20.
- The first `qwen3-embedding:4b` Armenian run failed with `ReadTimeout` at the
  default 120 s and was re-run with `--timeout 900`; the settings that affect
  results are unchanged.
- Indicative only: I wrote the questions, n is 14 per language, and the
  Armenian ones have not been reviewed by a native speaker.

## Reranker latency does not depend on the embedder

Median per 20-candidate query, all four runs of a language within 39.0-39.7 s
(Russian), 83.2-90.1 s (Armenian) and 17.3-19.4 s (English), i.e. about 2 s,
4.3 s and 0.9 s per pair. Cyrillic and Armenian text takes many more tokens
per chunk than English.

## Russian (EDB, 130 chunks)

| embedder | pool | vec hit@1 | vec hit@5 | vec MRR | rerank hit@1 | rerank hit@5 | rerank MRR |
|---|---|---|---|---|---|---|---|
| nomic-embed-text (current) | 9/14 | 3/14 | 5/14 | 0.32 | 9/14 | 9/14 | 0.64 |
| bge-m3 | 12/14 | 8/14 | 12/14 | 0.67 | 10/14 | 12/14 | 0.76 |
| qwen3-embedding:0.6b | 14/14 | 9/14 | 11/14 | 0.70 | 12/14 | 14/14 | 0.91 |
| qwen3-embedding:4b | 14/14 | 9/14 | 11/14 | 0.74 | 12/14 | 14/14 | 0.91 |
| nomic-embed-text-v2-moe | 12/14 | 8/14 | 10/14 | 0.62 | 10/14 | 12/14 | 0.77 |

## Armenian (IDBank, 59 chunks)

| embedder | pool | vec hit@1 | vec hit@5 | vec MRR | rerank hit@1 | rerank hit@5 | rerank MRR |
|---|---|---|---|---|---|---|---|
| nomic-embed-text (current) | 10/14 | 1/14 | 4/14 | 0.19 | 9/14 | 9/14 | 0.65 |
| bge-m3 | 14/14 | 10/14 | 13/14 | 0.82 | 12/14 | 13/14 | 0.89 |
| qwen3-embedding:0.6b | 14/14 | 8/14 | 12/14 | 0.68 | 12/14 | 13/14 | 0.89 |
| qwen3-embedding:4b | 14/14 | 7/14 | 13/14 | 0.65 | 12/14 | 13/14 | 0.89 |
| nomic-embed-text-v2-moe | 14/14 | 9/14 | 12/14 | 0.75 | 12/14 | 13/14 | 0.89 |

## English (Berkshire, 547 chunks)

| embedder | pool | vec hit@1 | vec hit@5 | vec MRR | rerank hit@1 | rerank hit@5 | rerank MRR |
|---|---|---|---|---|---|---|---|
| nomic-embed-text (current) | 12/14 | 5/14 | 9/14 | 0.50 | 10/14 | 12/14 | 0.79 |
| bge-m3 | 13/14 | 6/14 | 9/14 | 0.53 | 11/14 | 13/14 | 0.86 |
| qwen3-embedding:0.6b | 14/14 | 7/14 | 12/14 | 0.67 | 12/14 | 14/14 | 0.93 |
| qwen3-embedding:4b | 14/14 | 6/14 | 12/14 | 0.62 | 12/14 | 14/14 | 0.93 |
| nomic-embed-text-v2-moe | 12/14 | 4/14 | 8/14 | 0.43 | 10/14 | 12/14 | 0.79 |
