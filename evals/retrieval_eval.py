r"""Compare vector retrieval with vector retrieval plus an Ollama reranker.

Manual tool (needs a local Ollama with the embed and reranker models; not run
in CI). It mirrors the production path where it matters: the project's own PDF
parser and chunker with the ``Settings`` defaults, the same embed model, and
the production prompt-safety escaping and length limits on everything that
enters the reranker prompt. It differs in one respect: retrieval here is an
exact in-memory cosine ranking, not the pgvector HNSW index.

The reranker is the community GGUF of Qwen3-Reranker-4B, driven through
``/api/generate`` in raw mode with the Qwen prompt format; the score is
P(yes) among the first generated token's yes/no probabilities.

Usage::

    uv run python -m evals.retrieval_eval --pdf-dir evals/data/synthetic \
        --questions evals/questions/synthetic.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import math
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from evals.scoring import (
    contains_gold,
    hit_at,
    percentile,
    reciprocal_rank,
    yes_probability,
)
from evals.synthetic import Question, read_questions
from findocbot.config import Settings
from findocbot.infrastructure.chunking import ParagraphTokenChunker
from findocbot.infrastructure.pdf_parser import PyPDFParser
from findocbot.use_cases.answer_question import (
    _MAX_QUESTION_CHARS,
    _MAX_SOURCE_CHARS,
)
from findocbot.use_cases.prompt_safety import neutralize

DEFAULT_RERANK_MODEL = "awenleven/Qwen3-Reranker-4B:Q4_K_M"
# Fixed before the first run and not tuned against the question set.
INSTRUCTIONS = {
    "default": (
        "Given a web search query, retrieve relevant passages that answer "
        "the query"
    ),
    "task": (
        "Given a question about a company's annual report, retrieve the "
        "passage that answers it for that company and fiscal year"
    ),
}
_SYSTEM = (
    "Judge whether the Document meets the requirements based on the Query "
    "and the Instruct provided. Note that the answer can only be "
    '"yes" or "no".'
)
_PREFIX = f"<|im_start|>system\n{_SYSTEM}<|im_end|>\n<|im_start|>user\n"
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_EMBED_BATCH = 50
_KS = (1, 3, 5)


@dataclass(frozen=True)
class IndexedChunk:
    """A chunk of a PDF, as stored in the production index."""

    document: str
    text: str

    @property
    def title(self) -> str:
        """A document title derived from the file name."""
        return self.document.removesuffix(".pdf").replace("-", " ")


@dataclass
class Outcome:
    """The ranked hit flags of one question under one method."""

    question: Question
    variant: str
    method: str
    hits: list[bool]
    pool_has_gold: bool


@dataclass
class Timings:
    """Reranker latency samples, in seconds."""

    first_call: float = 0.0
    pairs: list[float] = field(default_factory=list)
    queries: list[float] = field(default_factory=list)


def load_chunks(pdf_dir: Path, settings: Settings) -> list[IndexedChunk]:
    """Parse and chunk every PDF in *pdf_dir* as production does."""
    parser = PyPDFParser()
    chunker = ParagraphTokenChunker(
        chunk_tokens=settings.chunk_tokens,
        overlap_ratio=settings.chunk_overlap_ratio,
    )
    chunks = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        text = parser.extract_text(pdf.read_bytes())
        chunks += [IndexedChunk(pdf.name, t) for t, _ in chunker.split(text)]
    return chunks


def is_hit(chunk: IndexedChunk, question: Question) -> bool:
    """A hit needs both the right document and the gold figure."""
    return chunk.document == question.document and contains_gold(
        chunk.text, question.gold
    )


def validate(
    questions: Sequence[Question],
    chunks: list[IndexedChunk],
    *,
    unique: bool = True,
) -> None:
    """Fail unless every gold figure is found only in the right document.

    With ``unique`` (the default, used for the synthetic corpus) it must sit
    in exactly one chunk. Real documents repeat facts, and the chunker's
    overlap copies the text at a chunk boundary into both neighbours, so
    ``unique=False`` accepts several chunks as long as all belong to the
    question's own document; any of them is then a correct answer.
    """
    problems = []
    for question in questions:
        found = [
            c.document for c in chunks if contains_gold(c.text, question.gold)
        ]
        ok = (
            found == [question.document]
            if unique
            else (bool(found) and set(found) == {question.document})
        )
        if not ok:
            problems.append(f"{question.id} {question.gold!r}: {found}")
    if problems:
        raise SystemExit("invalid questions:\n" + "\n".join(problems))


def indexed_text(chunk: IndexedChunk, variant: str) -> str:
    """The text embedded and reranked for a chunk under a variant."""
    return (
        chunk.text if variant == "plain" else f"{chunk.title}\n\n{chunk.text}"
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def reranker_prompt(query: str, passage: str, instruction: str) -> str:
    """The Qwen3-Reranker prompt; untrusted text is escaped as in prod."""
    safe_query = neutralize(query, _MAX_QUESTION_CHARS)
    safe_passage = neutralize(passage, _MAX_SOURCE_CHARS)
    return (
        f"{_PREFIX}<Instruct>: {instruction}\n<Query>: {safe_query}\n"
        f"<Document>: {safe_passage}{_SUFFIX}"
    )


class Ollama:
    """The few Ollama calls the evaluation needs."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        embed_model: str,
        rerank_model: str,
    ) -> None:
        """Remember the endpoint and models."""
        self._client = client
        self._base = base_url.rstrip("/")
        self.embed_model = embed_model
        self.rerank_model = rerank_model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in batches."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            response = await self._client.post(
                f"{self._base}/api/embed",
                json={
                    "model": self.embed_model,
                    "input": list(texts[start : start + _EMBED_BATCH]),
                },
            )
            response.raise_for_status()
            vectors += response.json()["embeddings"]
        return vectors

    async def rerank(
        self, query: str, passage: str, instruction: str
    ) -> tuple[float, float]:
        """Return (P(yes), seconds) for one query-passage pair."""
        started = time.perf_counter()
        response = await self._client.post(
            f"{self._base}/api/generate",
            json={
                "model": self.rerank_model,
                "prompt": reranker_prompt(query, passage, instruction),
                "raw": True,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 1,
                    "num_ctx": 4096,
                },
                "logprobs": True,
                "top_logprobs": 20,
            },
        )
        elapsed = time.perf_counter() - started
        response.raise_for_status()
        top = response.json()["logprobs"][0]["top_logprobs"]
        return yes_probability(
            (t["token"], t["logprob"]) for t in top
        ), elapsed

    async def describe(self) -> dict[str, str]:
        """Ollama version and the digests of the two models in use."""
        version = (await self._client.get(f"{self._base}/api/version")).json()
        tags = (await self._client.get(f"{self._base}/api/tags")).json()
        digests = {m["name"]: m["digest"][:12] for m in tags["models"]}
        return {
            "ollama": version["version"],
            self.embed_model: digests.get(self.embed_model, "?"),
            self.rerank_model: digests.get(self.rerank_model, "?"),
        }


def _hits(
    order: Sequence[int], chunks: list[IndexedChunk], q: Question
) -> list[bool]:
    return [is_hit(chunks[i], q) for i in order]


async def evaluate_variant(
    ollama: Ollama,
    variant: str,
    chunks: list[IndexedChunk],
    questions: Sequence[Question],
    pool: int,
    instructions: Sequence[str],
    timings: Timings,
) -> list[Outcome]:
    """Run vector and reranked retrieval for every question in a variant."""
    texts = [indexed_text(c, variant) for c in chunks]
    vectors = await ollama.embed(texts)
    query_vectors = await ollama.embed([q.question for q in questions])
    outcomes = []
    for question, qvec in zip(questions, query_vectors, strict=True):
        ranked = sorted(
            range(len(chunks)), key=lambda i: -cosine(qvec, vectors[i])
        )[:pool]
        vector_hits = _hits(ranked, chunks, question)
        pool_has_gold = any(vector_hits)
        outcomes.append(
            Outcome(question, variant, "vector", vector_hits, pool_has_gold)
        )
        for name in instructions:
            order = await rerank_pool(
                ollama, question, texts, ranked, INSTRUCTIONS[name], timings
            )
            outcomes.append(
                Outcome(
                    question,
                    variant,
                    f"rerank:{name}",
                    _hits(order, chunks, question),
                    pool_has_gold,
                )
            )
    return outcomes


async def rerank_pool(
    ollama: Ollama,
    question: Question,
    texts: list[str],
    pool: list[int],
    instruction: str,
    timings: Timings,
) -> list[int]:
    """Order the pool by reranker score, best first (stable on ties)."""
    scores = []
    started = time.perf_counter()
    for index in pool:
        score, seconds = await ollama.rerank(
            question.question, texts[index], instruction
        )
        if timings.first_call == 0.0:
            timings.first_call = seconds
        else:
            timings.pairs.append(seconds)
        scores.append(score)
    timings.queries.append(time.perf_counter() - started)
    order = sorted(range(len(pool)), key=lambda i: -scores[i])
    return [pool[i] for i in order]


def _fraction(count: int, total: int) -> str:
    return f"{count}/{total}"


def summarize(outcomes: list[Outcome], variant: str, method: str) -> list[str]:
    """Table cells for one (variant, method): n, pool, hit@k, MRR."""
    rows = [o for o in outcomes if o.variant == variant and o.method == method]
    cells = [str(len(rows))]
    cells.append(_fraction(sum(o.pool_has_gold for o in rows), len(rows)))
    for k in _KS:
        cells.append(
            _fraction(sum(hit_at(o.hits, k) for o in rows), len(rows))
        )
    mrr = (
        statistics.fmean(reciprocal_rank(o.hits) for o in rows)
        if rows
        else 0.0
    )
    cells.append(f"{mrr:.2f}")
    return cells


def format_report(
    outcomes: list[Outcome],
    meta: dict[str, str],
    timings: Timings,
    pool: int,
    label: str,
) -> str:
    """Render the results as markdown."""
    variants = list(dict.fromkeys(o.variant for o in outcomes))
    methods = list(dict.fromkeys(o.method for o in outcomes))
    categories = list(dict.fromkeys(o.question.category for o in outcomes))
    lines = [f"# Retrieval evaluation: {label}", ""]
    lines += [f"- {key}: `{value}`" for key, value in meta.items()]
    lines += [
        f"- candidate pool: top {pool} by exact cosine (not pgvector HNSW)",
        (
            "- counts are hits/questions; `pool` is how many questions have "
            "the gold chunk in the pool, the ceiling for any reranker"
        ),
        "",
    ]
    for variant in variants:
        lines += [f"## Variant: {variant}", ""]
        lines += [
            "| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |"
        ]
        lines += ["|---|---|---|---|---|---|---|---|"]
        for category in [*categories, "all"]:
            subset = [
                o for o in outcomes if category in ("all", o.question.category)
            ]
            for method in methods:
                cells = summarize(subset, variant, method)
                lines.append(
                    f"| {category} | {method} | " + " | ".join(cells) + " |"
                )
        lines.append("")
    lines += ["## Reranker latency", ""]
    if timings.pairs:
        pair_median = statistics.median(timings.pairs)
        pair_p90 = percentile(timings.pairs, 0.9)
        query_median = statistics.median(timings.queries)
        query_p90 = percentile(timings.queries, 0.9)
        lines += [
            f"- first call (incl. any model load): {timings.first_call:.1f}s",
            (
                f"- per pair, warm: median {pair_median:.2f}s, "
                f"p90 {pair_p90:.2f}s (n={len(timings.pairs)})"
            ),
            (
                f"- per query ({pool} pairs): median {query_median:.1f}s, "
                f"p90 {query_p90:.1f}s"
            ),
        ]
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> str:
    """Run the evaluation and return the markdown report."""
    settings = Settings(
        _env_file=None, postgres_dsn="postgresql://u:p@localhost/db"
    )
    questions = read_questions(args.questions)
    chunks = load_chunks(args.pdf_dir, settings)
    validate(questions, chunks, unique=args.gold == "unique")
    if args.validate_only:
        return f"{len(questions)} questions are valid for {args.pdf_dir}\n"
    timings = Timings()
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        ollama = Ollama(
            client,
            args.ollama_url,
            args.embed_model or settings.ollama_embed_model,
            args.rerank_model,
        )
        meta = await ollama.describe()
        meta["documents"] = str(len({c.document for c in chunks}))
        meta["chunks"] = str(len(chunks))
        meta["questions"] = str(len(questions))
        outcomes: list[Outcome] = []
        for variant in args.variants:
            outcomes += await evaluate_variant(
                ollama,
                variant,
                chunks,
                questions,
                args.pool,
                args.instructions,
                timings,
            )
    return format_report(outcomes, meta, timings, args.pool, args.label)


def parse_args() -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--label", default="synthetic")
    parser.add_argument(
        "--gold",
        choices=("unique", "any"),
        default="unique",
        help="unique: gold in exactly one chunk; any: in one or more chunks "
        "of the question's document (real PDFs: overlap and repeated facts)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="check the questions against the PDFs and stop (no Ollama)",
    )
    parser.add_argument("--pool", type=int, default=20)
    parser.add_argument(
        "--variants",
        type=lambda v: v.split(","),
        default=["plain"],
        help="comma list of: plain, titled (file name added to each chunk)",
    )
    parser.add_argument(
        "--instructions",
        type=lambda v: v.split(","),
        default=["default"],
        help=f"comma list of: {', '.join(INSTRUCTIONS)}",
    )
    parser.add_argument(
        "--ollama-url",
        default=Settings.model_fields["ollama_base_url"].default,
    )
    parser.add_argument("--embed-model", default=None)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    report = asyncio.run(run(args))
    print(report)
    if args.validate_only:
        return
    out: Path = args.out or Path(
        f"evals/results/{datetime.date.today():%Y-%m-%d}-{args.label}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
