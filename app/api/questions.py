from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application.chunking import StructuredFilingChunker
from app.application.ingestion import FilingIngestionService
from app.application.question_answer import (
    DenseRetrievalService,
    LocalGenerationProvider,
    PromptBuilder,
    QueryUnderstandingService,
    QuestionAnswerService,
)
from app.application.sec_filings import SECFilingService
from app.application.structured_filings import FilingDocumentProcessingService
from app.config import settings
from app.infrastructure.bm25 import BM25TextRepresentationBuilder
from app.infrastructure.embeddings import SentenceTransformerEmbeddingProvider
from app.infrastructure.file_chunk_index import FileSystemChunkIndexRepository
from app.infrastructure.tokenization import TiktokenTokenizer
from app.infrastructure.vector_index import LocalVectorIndex

router = APIRouter(tags=["questions"])


@dataclass(frozen=True)
class QuestionRequest:
    question: str


def _ensure_filing_is_indexed(
    *,
    question: str,
    request: Request,
    embedding_provider: SentenceTransformerEmbeddingProvider,
    vector_index: LocalVectorIndex,
) -> None:
    parser = QueryUnderstandingService()
    parsed = parser.parse_question(question)
    ticker = parsed.ticker or {
        "apple": "AAPL",
        "microsoft": "MSFT",
        "amazon": "AMZN",
        "nvidia": "NVDA",
        "alphabet": "GOOG",
        "meta": "META",
        "tesla": "TSLA",
    }.get((parsed.company_name or "").lower())
    filing_type = parsed.filing_type or "10-K"
    if ticker is None:
        return
    if vector_index.document_count > 0:
        return

    sec_service = SECFilingService(request.app.state.sec_client)
    structured = FilingDocumentProcessingService(
        sec_service,
        request.app.state.filing_parser,
    ).fetch_and_parse(ticker, filing_type)
    chunking = StructuredFilingChunker(
        settings.chunking,
        TiktokenTokenizer(settings.chunking.tokenizer_encoding),
    )
    ingestion = FilingIngestionService(
        filing_service=sec_service,
        parser=request.app.state.filing_parser,
        chunker=chunking,
        bm25_builder=BM25TextRepresentationBuilder(),
        index_repository=FileSystemChunkIndexRepository(Path(settings.vector_index_directory)),
        embedding_provider=embedding_provider,
        vector_index=vector_index,
        storage_directory=settings.vector_index_directory,
    )
    ingestion.ingest_filing(structured)


@router.post("/questions")
def ask_question(payload: QuestionRequest, request: Request) -> JSONResponse:
    embedding_provider = getattr(request.app.state, "embedding_provider", None)
    vector_index = getattr(request.app.state, "vector_index", None)
    if embedding_provider is None or vector_index is None:
        embedding_provider = SentenceTransformerEmbeddingProvider(
            model_name=settings.embedding_model_name,
            cache_dir=settings.embedding_cache_dir,
        )
        vector_index = LocalVectorIndex(
            model_name=settings.embedding_model_name,
            dimension=embedding_provider.embedding_dimension,
            directory=Path(settings.vector_index_directory),
        )
        request.app.state.embedding_provider = embedding_provider
        request.app.state.vector_index = vector_index

    _ensure_filing_is_indexed(
        question=payload.question,
        request=request,
        embedding_provider=embedding_provider,
        vector_index=vector_index,
    )

    service = QuestionAnswerService(
        question_parser=QueryUnderstandingService(),
        retriever=DenseRetrievalService(
            embedding_provider=embedding_provider,
            vector_index=vector_index,
            top_k=settings.rag_top_k,
            relevance_threshold=settings.rag_min_relevance_score,
        ),
        prompt_builder=PromptBuilder(prompt_version=settings.rag_prompt_version),
        generation_provider=LocalGenerationProvider(
            model_name=settings.generation_model_name,
            max_new_tokens=settings.generation_max_new_tokens,
            temperature=settings.generation_temperature,
        ),
        prompt_version=settings.rag_prompt_version,
        relevance_threshold=settings.rag_min_relevance_score,
    )
    response = service.answer_question(payload.question)
    return JSONResponse(content={
        "status": response.status,
        "question": response.question,
        "answer": response.answer,
        "citations": [asdict(citation) for citation in response.citations],
        "refusal_reason": response.refusal_reason,
        "model_id": response.model_id,
        "prompt_version": response.prompt_version,
    })
