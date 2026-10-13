from __future__ import annotations

from dataclasses import dataclass

from app.application.question_answer import (
    AnswerResponse,
    CitationRecord,
    QueryUnderstandingService,
    QuestionAnswerService,
)
from app.domain.chunks import Chunk, ChunkMetadata, ChunkProvenance, ChunkType


@dataclass(frozen=True)
class FakeEmbeddingProvider:
    model: str = "test-model"
    dimension: int = 3

    @property
    def embedding_model(self) -> str:
        return self.model

    @property
    def embedding_dimension(self) -> int:
        return self.dimension

    def embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


@dataclass(frozen=True)
class FakeGenerationProvider:
    output: str = "Apple discusses competition and supply-chain risk [S1]."

    def generate(self, prompt: str) -> str:
        return self.output


class FakeRetriever:
    def __init__(self) -> None:
        chunk = Chunk(
            chunk_id="chunk-1",
            chunk_type=ChunkType.NARRATIVE,
            content="Apple faces competition and supply-chain constraints.",
            metadata=ChunkMetadata(
                company="Apple Inc.",
                ticker="AAPL",
                cik="0000320193",
                accession_number="0000320193-25-000001",
                form_type="10-K",
                filing_date="2025-02-01",
                period_of_report="FY2025",
                part="Item 1A",
                item="Risk Factors",
                section="Risk Factors",
                subsection=None,
                document_id="aapl-2025.htm",
                source_element_ids=("risk-1",),
                source_url="https://www.sec.gov/aapl-2025.htm",
                html_anchors=("risk-1",),
                page_start=None,
                page_end=None,
            ),
            provenance=ChunkProvenance(
                filing_id="0000320193-25-000001",
                document_id="aapl-2025.htm",
                source_element_ids=("risk-1",),
                source_url="https://www.sec.gov/aapl-2025.htm",
                html_anchors=("risk-1",),
                start_offset=None,
                end_offset=None,
                page_start=None,
                page_end=None,
                source_references=(),
            ),
            relationships=None,
            chunking_version="1",
        )
        self.chunk = chunk

    def search(self, query_vector: list[float], *, top_k: int = 5):
        return [
            {
                "chunk_id": self.chunk.chunk_id,
                "score": 0.92,
                "chunk": self.chunk,
                "metadata": self.chunk.metadata,
                "provenance": self.chunk.provenance,
            }
        ]


def test_query_understanding_parses_company_filing_and_period() -> None:
    parsed = QueryUnderstandingService().parse_question(
        "What were Apple's main risk factors in its FY2025 10-K?"
    )

    assert parsed.company_name == "Apple"
    assert parsed.ticker == "AAPL"
    assert parsed.filing_type == "10-K"
    assert parsed.fiscal_period == "FY2025"
    assert "risk factors" in parsed.underlying_question.lower()


def test_question_service_answers_with_citation_and_status() -> None:
    service = QuestionAnswerService(
        question_parser=QueryUnderstandingService(),
        generation_provider=FakeGenerationProvider(),
        retriever=FakeRetriever(),
        prompt_version="rag_answer_v1",
        relevance_threshold=0.10,
    )

    response = service.answer_question("What were Apple's main risk factors in its FY2025 10-K?")

    assert response.status == "answered"
    assert response.answer == "Apple discusses competition and supply-chain risk [S1]."
    assert response.citations[0].label == "S1"
    assert response.citations[0].chunk_id == "chunk-1"
    assert isinstance(response, AnswerResponse)
    assert isinstance(response.citations[0], CitationRecord)
    assert response.prompt_version == "rag_answer_v1"
