# Verification: capping a chunk at ten characters per token (2026-10-16)

**Change.** `ParagraphTokenChunker.split` ends by cutting any chunk longer than ten
characters per chunk token (3,000 at the default `CHUNK_TOKENS=300`) at a paragraph, line,
sentence mark or space, else at the ceiling. Text that is within it is untouched.

**Method.** The `verify` skill as a differential: the same throwaway Postgres and stub
Ollama, the app run first from `master` and then from the worktree of this branch (each
with its own virtual environment; the chunker module path was printed for both). The stub
refuses, with Ollama's 400 body, any `/api/embed` input over 3,000 characters, which is
what a real window does to a chunk that is too long. Two uploads per run: the sample
report, and a PDF of 60 paragraphs of 400 letters each with no spaces (built with
`tests.factories.build_pdf_bytes`).

| Upload | Before (master) | After (this branch) |
|--------|-----------------|---------------------|
| `sample.pdf` | `ready`; 5 chunks, longest 1,170 characters | `ready`; 5 chunks, longest 1,170 characters |
| `glued.pdf` | `failed`: "A passage of the document is too long for the embedding model..."; 0 chunks | `ready`; 9 chunks, longest **2,988** characters |

**Verdict: PASS.** The ordinary document is unchanged and the unbreakable one now ingests.

## Not through the stub

Real reports, production chunker, the digest of the whole chunk list (`repr` of the
`(text, section)` pairs):

| Report | Chunks | Longest | Digest before | Digest after |
|--------|--------|---------|---------------|--------------|
| English | 547 | 2,103 chars | `7b2c98a89c54` | `7b2c98a89c54` |
| Russian | 130 | 2,259 chars | `c4e37d29f5bf` | `c4e37d29f5bf` |
| Armenian | 59 | 2,343 chars | `69ab946bd998` | `69ab946bd998` |

Synthetic texts that fool the chunker's word count (random characters, so the token
figures are pessimistic), the longest chunk and its tokens by the real embedder's
tokenizer:

| Text | Before | After |
|------|--------|-------|
| Chinese, no punctuation or spaces | 1 chunk, 90,118 chars, over 32,768 tokens | 60 chunks, longest 1,500 chars, 2,255 tokens |
| English with the spaces lost | 8 chunks, longest 17,502 chars, 4,470 tokens | 48 chunks, longest 2,792 chars, 702 tokens |
| Chinese with punctuation | 25 chunks, longest 3,058 chars, 4,500 tokens | 49 chunks, longest 2,888 chars, 4,263 tokens |

Not measured: real documents in Thai or Chinese.
