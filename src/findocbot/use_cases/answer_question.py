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
        answer = await self._provider.generate(prompt)

        await self._history.add_turn(
            ChatTurn.create(
                session_id=session_id,
                question=clean_question,
                answer=answer,
            )
        )
        return AskResponseDTO(answer=answer, sources=sources)

    @staticmethod
    def _build_prompt(
        question: str,
        sources: list,
        recent_turns: list[ChatTurn],
    ) -> str:
        """Build RAG prompt with context and short history."""
        history_text = "\n".join(
            (f"Q: {turn.question}\nA: {turn.answer}") for turn in recent_turns
        )
        context_text = "\n\n".join(
            f"[score={source.score:.4f}] {source.text}" for source in sources
        )
        return (
            "You are an assistant for financial documents.\n"
            "Use only the provided context and chat history.\n"
            "If context is insufficient, say so explicitly.\n\n"
            f"Chat history:\n{history_text or 'No prior turns.'}\n\n"
            f"Context:\n{context_text or 'No relevant chunks found.'}\n\n"
            f"Question: {question}\n"
            "Answer:"
        )
