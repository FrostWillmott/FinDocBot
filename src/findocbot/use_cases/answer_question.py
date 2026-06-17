"""Answer question from retrieved context use case."""

from findocbot.domain.entities import ChatTurn
from findocbot.domain.exceptions import InvalidQueryError
from findocbot.use_cases.dto import AskResponseDTO
from findocbot.use_cases.ports import (
    ChatHistoryRepositoryPort,
    ModelProviderGateway,
)
from findocbot.use_cases.search_similar_chunks import (
    SearchSimilarChunksUseCase,
)

# JSON Schema for the structured answer returned by the LLM.
_ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": (
                "Concise answer to the user question"
                " based solely on the provided context."
            ),
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": (
                "Self-assessed confidence given the available context."
            ),
        },
    },
    "required": ["answer", "confidence"],
}


class AnswerQuestionUseCase:
    """Generate answer based on document chunks and short history."""

    def __init__(
        self,
        provider: ModelProviderGateway,
        search_use_case: SearchSimilarChunksUseCase,
        history: ChatHistoryRepositoryPort,
        max_history_pairs: int = 5,
    ) -> None:
        """Store dependencies for RAG answer generation."""
        self._provider = provider
        self._search_use_case = search_use_case
        self._history = history
        self._max_history_pairs = max_history_pairs

    async def execute(
        self,
        session_id: str,
        question: str,
        top_k: int,
    ) -> AskResponseDTO:
        """Generate contextual answer and store interaction."""
        clean_question = question.strip()
        if not clean_question:
            raise InvalidQueryError("Question cannot be empty.")

        sources = await self._search_use_case.execute(
            clean_question, top_k=top_k
        )
        recent_turns = await self._history.list_recent(
            session_id=session_id,
            limit=self._max_history_pairs,
        )
        prompt = self._build_prompt(
            question=clean_question,
            sources=sources,
            recent_turns=recent_turns,
        )
        structured = await self._provider.generate_structured(
            prompt, _ANSWER_SCHEMA
        )
        answer: str = structured["answer"]
        confidence: str = structured.get("confidence", "medium")

        await self._history.add_turn(
            ChatTurn.create(
                session_id=session_id,
                question=clean_question,
                answer=answer,
            )
        )
        return AskResponseDTO(
            answer=answer, confidence=confidence, sources=sources
        )

    @staticmethod
    def _build_prompt(
        question: str,
        sources: list,
        recent_turns: list[ChatTurn],
    ) -> str:
        """Build RAG prompt that requests a structured JSON response."""
        history_text = "\n".join(
            f"Q: {turn.question}\nA: {turn.answer}" for turn in recent_turns
        )
        context_text = "\n\n".join(
            f"[score={source.score:.4f}] {source.text}" for source in sources
        )
        return (
            "You are an assistant for financial documents.\n"
            "Use only the provided context and chat history to answer.\n"
            "If the context is insufficient, say so in the answer field.\n"
            "Reply with a JSON object containing:\n"
            "  - answer: your concise answer (string)\n"
            "  - confidence: one of high / medium / low\n\n"
            f"Chat history:\n{history_text or 'No prior turns.'}\n\n"
            f"Context:\n{context_text or 'No relevant chunks found.'}\n\n"
            f"Question: {question}"
        )
