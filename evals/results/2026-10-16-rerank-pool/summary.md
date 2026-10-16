# Reranking a smaller candidate pool

The retrieval evaluation (`evals/README.md`) with `--pool 5` and `--pool 10`, against the
`--pool 20` runs of `2026-10-16-embedders/` (`qwen3-embedding-0.6b-*.md`): same questions,
PDFs, chunking, embedder (`qwen3-embedding:0.6b`), reranker
(`Qwen3-Reranker-4B:Q4_K_M`), `--gold any` and the `default` instruction. Only the number
of vector-search candidates handed to the reranker changes. The raw reports sit next to
this file as `<language>-pool<N>.md`.

- `gold in pool` is how many of the 14 questions have the right chunk among the
  candidates: the ceiling for any reranker.
- `vectors only` is the plain cosine order; its MRR counts ranks inside the pool, so
  compare hit@1, not MRR, across pool sizes.
- The reranker time is the median and p90 for one query over its candidates, measured
  by the harness (reranker window 4096; the application uses 8192).


## English (Berkshire, 547 chunks)

| method | gold in pool | hit@1 | hit@3 | hit@5 | MRR | reranker time per query (median / p90) |
|---|---|---|---|---|---|---|
| vectors only | - | 7/14 | 11/14 | 12/14 | 0.66 | - |
| rerank top 5 | 12/14 | 10/14 | 12/14 | 12/14 | 0.79 | 4 s / 6 s |
| rerank top 10 | 13/14 | 11/14 | 13/14 | 13/14 | 0.86 | 9 s / 10 s |
| rerank top 20 | 14/14 | 12/14 | 14/14 | 14/14 | 0.93 | 17 s / 21 s |

## Russian (EDB, 130 chunks)

| method | gold in pool | hit@1 | hit@3 | hit@5 | MRR | reranker time per query (median / p90) |
|---|---|---|---|---|---|---|
| vectors only | - | 9/14 | 9/14 | 11/14 | 0.68 | - |
| rerank top 5 | 11/14 | 10/14 | 10/14 | 11/14 | 0.73 | 9 s / 10 s |
| rerank top 10 | 13/14 | 11/14 | 12/14 | 13/14 | 0.84 | 18 s / 27 s |
| rerank top 20 | 14/14 | 12/14 | 13/14 | 14/14 | 0.91 | 39 s / 43 s |

## Armenian (IDBank, 59 chunks)

| method | gold in pool | hit@1 | hit@3 | hit@5 | MRR | reranker time per query (median / p90) |
|---|---|---|---|---|---|---|
| vectors only | - | 8/14 | 10/14 | 12/14 | 0.66 | - |
| rerank top 5 | 12/14 | 10/14 | 11/14 | 12/14 | 0.75 | 22 s / 25 s |
| rerank top 10 | 14/14 | 11/14 | 12/14 | 13/14 | 0.85 | 49 s / 63 s |
| rerank top 20 | 14/14 | 12/14 | 13/14 | 13/14 | 0.89 | 88 s / 94 s |

## How much of the full gain a smaller pool keeps

The gain is hit@1 over vectors only; "full" is the pool of 20.

| | Full gain | Top 5 | Top 10 |
|---|---|---|---|
| English | +5 | +3 (60%) at a quarter of the time | +4 (80%) at half |
| Russian | +3 | +1 (33%) at a quarter of the time | +2 (67%) at half |
| Armenian | +4 | +2 (50%) at a quarter of the time | +3 (75%) at half |

## Read before relying on it

- Indicative only: I wrote the questions, n is 14 per language, and one question moves a
  figure by 7 points.
- The seconds were taken on a 16 GB machine with other work running (tests, stubbed
  checks, chunk measurements, a swap that was in use) and with the embedder resident at
  its maximum window, which this harness does not limit. The runs overlapped with that
  work unevenly, so the pool 5 and pool 10 seconds may be inflated against the pool 20
  ones; the order between pool sizes and between languages is what to trust.
- The default `RERANK_TIMEOUT_SECONDS` is 30. Against these medians, pool 20 fits for
  English only, pool 10 for English and Russian (p90 27 s), pool 5 for all three.
