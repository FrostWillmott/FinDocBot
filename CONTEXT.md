# FinDocBot

Question answering over uploaded financial PDFs: a client uploads reports, the system makes them searchable, and answers questions with cited sources from them.

## Language

**Document**:
A PDF held by the system. Uploading the same bytes again yields the same Document.
_Avoid_: file, report

**Chunk**:
A passage of a Document, labelled with its section when it has one, retrievable as evidence for an answer.
_Avoid_: fragment, passage

**Upload**:
The act of a client sending a PDF to the system. It is accepted at once and says nothing about whether the Document is searchable yet.
_Avoid_: import

**Ingestion**:
The background run that turns an uploaded Document into searchable Chunks and settles its Document status.
_Avoid_: processing, indexing

**Document status**:
Where a Document stands in its Ingestion: **pending** (accepted, not yet searchable), **ready** (searchable), or **failed** (Ingestion ended, with a reason a client may see).
_Avoid_: state
