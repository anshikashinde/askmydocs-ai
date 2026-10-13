from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.application.errors import ApplicationError
from app.config import settings
from app.domain.chunks import Chunk, ChunkMetadata, ChunkProvenance

SUPPORTED_FILING_TYPES = {"10-K", "10-Q"}
COMPANY_ALIASES: dict[str, str] = {
    "apple": "Apple",
    "apple inc": "Apple",
    "aapl": "Apple",
    "microsoft": "Microsoft",
    "microsoft corp": "Microsoft",
    "msft": "Microsoft",
    "amazon": "Amazon",
    "amzn": "Amazon",
    "nvidia": "NVIDIA",
    "nvda": "NVIDIA",
    "alphabet": "Alphabet",
    "googl": "Alphabet",
    "meta": "Meta",
    "meta platforms": "Meta",
    "meta platforms inc": "Meta",
    "tsla": "Tesla",
}


class GenerationProvider(Protocol):
    def generate(self, prompt: str) -> str: ...


class RetrievalProvider(Protocol):
    def search(
        self, question: str, *, filing_scope: str | None = None
    ) -> Sequence[Any]: ...


@dataclass(frozen=True)
class ParsedQuery:
    original_question: str
    company_name: str | None
    ticker: str | None
    filing_type: str | None
    fiscal_period: str | None
    underlying_question: str
    unresolved_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class CitationRecord:
    label: str
    chunk_id: str
    company: str | None
    ticker: str | None
    form_type: str | None
    filing_period: str | None
    section: str | None
    source_url: str | None
    accession_number: str | None
    excerpt: str | None


@dataclass(frozen=True)
class AnswerResponse:
    status: str
    question: str
    answer: str | None
    citations: tuple[CitationRecord, ...] = ()
    refusal_reason: str | None = None
    model_id: str | None = None
    prompt_version: str = "rag_answer_v1"


class QueryUnderstandingService:
    def parse_question(self, question: str) -> ParsedQuery:
        cleaned = (question or "").strip()
        if not cleaned:
            raise ValueError("Question cannot be empty")

        normalized = re.sub(r"\s+", " ", cleaned)
        company_name, ticker = self._detect_company(normalized)
        filing_type = self._detect_filing_type(normalized)
        fiscal_period = self._detect_period(normalized)

        underlying = normalized
        for phrase in self._remove_phrases(normalized, company_name, ticker, filing_type, fiscal_period):
            underlying = re.sub(re.escape(phrase), " ", underlying, flags=re.IGNORECASE)
        underlying = re.sub(r"\s+", " ", underlying)
        underlying = underlying.strip(" ,;:-")

        unresolved: list[str] = []
        if company_name is None and ticker is None:
            unresolved.append("company")
        if filing_type is None:
            unresolved.append("filing type")

        return ParsedQuery(
            original_question=cleaned,
            company_name=company_name,
            ticker=ticker,
            filing_type=filing_type,
            fiscal_period=fiscal_period,
            underlying_question=underlying or cleaned,
            unresolved_fields=tuple(unresolved),
        )

    def _detect_company(self, text: str) -> tuple[str | None, str | None]:
        for alias, company in sorted(COMPANY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
            if pattern.search(text):
                if alias.isupper() and alias not in {"AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "TSLA"}:
                    continue
                ticker = self._ticker_for_company(company)
                return company, ticker
        return None, None

    def _detect_filing_type(self, text: str) -> str | None:
        match = re.search(r"\b10[-\s]?K\b", text, flags=re.IGNORECASE)
        if match:
            return "10-K"
        match = re.search(r"\b10[-\s]?Q\b", text, flags=re.IGNORECASE)
        if match:
            return "10-Q"
        return None

    def _detect_period(self, text: str) -> str | None:
        match = re.search(r"(?:FY|fiscal year)\s*(20\d{2})", text, flags=re.IGNORECASE)
        if match:
            return f"FY{match.group(1)}"
        match = re.search(r"\b(20\d{2})\b", text)
        if match and ("10-K" in text.upper() or "10-Q" in text.upper()):
            return f"FY{match.group(1)}"
        return None

    def _remove_phrases(
        self,
        text: str,
        company_name: str | None,
        ticker: str | None,
        filing_type: str | None,
        fiscal_period: str | None,
    ) -> list[str]:
        phrases: list[str] = []
        if company_name is not None:
            phrases.append(company_name)
        if ticker is not None:
            phrases.append(ticker)
        if filing_type is not None:
            phrases.append(filing_type)
        if fiscal_period is not None:
            phrases.append(fiscal_period)

        for alias, _company in COMPANY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", text, flags=re.IGNORECASE) and alias not in {
                "apple",
                "aapl",
                "microsoft",
                "msft",
                "amazon",
                "amzn",
                "nvidia",
                "nvda",
                "googl",
                "meta",
                "tsla",
            }:
                phrases.append(alias)

        return [phrase for phrase in dict.fromkeys(phrases) if phrase]

    @staticmethod
    def _ticker_for_company(company_name: str) -> str | None:
        mapping = {
            "Apple": "AAPL",
            "Microsoft": "MSFT",
            "Amazon": "AMZN",
            "NVIDIA": "NVDA",
            "Alphabet": "GOOG",
            "Meta": "META",
            "Tesla": "TSLA",
        }
        return mapping.get(company_name)


@dataclass(frozen=True)
class ResolvedFiling:
    company_name: str
    ticker: str | None
    filing_type: str
    fiscal_period: str | None
    filing_id: str | None = None


class FilingResolutionService:
    def resolve(self, parsed_query: ParsedQuery) -> ResolvedFiling:
        company_name = parsed_query.company_name or "Unknown Company"
        ticker = parsed_query.ticker
        filing_type = parsed_query.filing_type or "10-K"
        if filing_type not in SUPPORTED_FILING_TYPES:
            raise ValueError(f"Unsupported filing type: {filing_type}")
        if company_name == "Unknown Company" and ticker is None:
            raise ValueError("Question must identify a company or ticker")
        return ResolvedFiling(
            company_name=company_name,
            ticker=ticker,
            filing_type=filing_type,
            fiscal_period=parsed_query.fiscal_period,
        )


@dataclass(frozen=True)
class RetrievalRecord:
    chunk_id: str
    score: float
    chunk: Chunk | None
    metadata: ChunkMetadata | None
    provenance: ChunkProvenance | None


class DenseRetrievalService:
    def __init__(
        self,
        *,
        embedding_provider: Any | None,
        vector_index: Any | None,
        top_k: int = 5,
        relevance_threshold: float | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_index = vector_index
        self.top_k = top_k
        self.relevance_threshold = relevance_threshold

    def search(
        self, question: str, *, filing_scope: str | None = None
    ) -> list[RetrievalRecord]:
        if self._embedding_provider is None or self._vector_index is None:
            raise ApplicationError("A vector index and embedding provider are required for retrieval")

        query_vector = self._embedding_provider.embed_text(question)
        results = self._vector_index.search(query_vector, top_k=self.top_k)
        filtered: list[RetrievalRecord] = []
        for result in results:
            metadata = result.metadata if hasattr(result, "metadata") else None
            provenance = result.provenance if hasattr(result, "provenance") else None
            if filing_scope is not None:
                filing_id = metadata.accession_number if metadata is not None else None
                if filing_id is None:
                    filing_id = provenance.filing_id if provenance is not None else None
                if filing_id != filing_scope:
                    continue
            filtered.append(
                RetrievalRecord(
                    chunk_id=result.chunk_id,
                    score=float(result.score),
                    chunk=result.chunk if hasattr(result, "chunk") else None,
                    metadata=metadata,
                    provenance=provenance,
                )
            )

        if not filtered:
            return []
        if self.relevance_threshold is not None and filtered[0].score < self.relevance_threshold:
            return []
        return filtered


class PromptBuilder:
    def __init__(self, prompt_version: str = "rag_answer_v1", prompt_dir: str | Path | None = None) -> None:
        self.prompt_version = prompt_version
        base_dir = Path(prompt_dir) if prompt_dir is not None else Path(__file__).resolve().parents[2] / "prompts"
        self._prompt_path = base_dir / f"{self.prompt_version}.txt"

    def build(self, parsed_query: ParsedQuery, evidence: Sequence[RetrievalRecord]) -> str:
        if not self._prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {self._prompt_path}")
        template = self._prompt_path.read_text(encoding="utf-8")
        serialized = self._serialize_evidence(evidence)
        return template.format(
            question=parsed_query.original_question,
            underlying_question=parsed_query.underlying_question,
            evidence=serialized,
        )

    def _serialize_evidence(self, evidence: Sequence[RetrievalRecord]) -> str:
        if not evidence:
            return "No relevant evidence retrieved."

        chunks: list[str] = []
        for index, record in enumerate(evidence, start=1):
            label = f"S{index}"
            metadata = record.metadata
            title = (
                f"{metadata.company or 'Unknown company'} — "
                f"{metadata.form_type or 'Unknown filing'} — "
                f"{metadata.period_of_report or 'Unknown period'}"
                if metadata else "Unknown source"
            )
            source = metadata.source_url if metadata else None
            chunk_text = record.chunk.content if record.chunk is not None else "(no chunk text)"
            chunks.append(
                f"[{label}] {title}\n"
                f"Source: {source or 'N/A'}\n"
                f"Chunk ID: {record.chunk_id}\n"
                f"Evidence:\n{chunk_text}\n"
            )
        return "\n".join(chunks)


class LocalGenerationProvider:
    def __init__(
        self,
        model_name: str = "fake-model",
        *,
        max_new_tokens: int = 200,
        temperature: float = 0.0,
    ) -> None:
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

    def generate(self, prompt: str) -> str:
        if self.model_name == "fake-model":
            return "Apple discusses competition and supply-chain risk [S1]."
        try:
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ApplicationError("Local generation requires transformers to be installed") from exc

        generator = pipeline(
            "text-generation",
            model=self.model_name,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
        )
        output = generator(prompt, do_sample=self.temperature > 0)[0]["generated_text"]
        return str(output)


class QuestionAnswerService:
    def __init__(
        self,
        *,
        question_parser: QueryUnderstandingService | None = None,
        filing_resolver: FilingResolutionService | None = None,
        retriever: RetrievalProvider | None = None,
        prompt_builder: PromptBuilder | None = None,
        generation_provider: GenerationProvider | None = None,
        prompt_version: str = "rag_answer_v1",
        relevance_threshold: float | None = None,
    ) -> None:
        self.question_parser = question_parser or QueryUnderstandingService()
        self.filing_resolver = filing_resolver or FilingResolutionService()
        self.retriever = retriever
        self.prompt_builder = prompt_builder or PromptBuilder(prompt_version=prompt_version)
        self.generation_provider = generation_provider or LocalGenerationProvider(model_name=settings.generation_model_name)
        self.prompt_version = prompt_version
        self.relevance_threshold = relevance_threshold

    @staticmethod
    def _coerce_evidence(evidence: Sequence[dict[str, Any] | RetrievalRecord]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for entry in evidence:
            if isinstance(entry, dict):
                converted.append(entry)
                continue
            converted.append(
                {
                    "chunk_id": entry.chunk_id,
                    "score": entry.score,
                    "chunk": entry.chunk,
                    "metadata": entry.metadata,
                    "provenance": entry.provenance,
                }
            )
        return converted

    @staticmethod
    def _to_records(evidence: Sequence[dict[str, Any]]) -> list[RetrievalRecord]:
        records: list[RetrievalRecord] = []
        for entry in evidence:
            records.append(
                RetrievalRecord(
                    chunk_id=str(entry.get("chunk_id") or ""),
                    score=float(entry.get("score") or 0.0),
                    chunk=entry.get("chunk"),
                    metadata=entry.get("metadata"),
                    provenance=entry.get("provenance"),
                )
            )
        return records

    def answer_question(self, question: str) -> AnswerResponse:
        if not question or not question.strip():
            return AnswerResponse(
                status="unsupported_request",
                question=question,
                answer=None,
                refusal_reason="Question is empty.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        try:
            parsed = self.question_parser.parse_question(question)
        except ValueError as exc:
            return AnswerResponse(
                status="clarification_required",
                question=question,
                answer=None,
                refusal_reason=str(exc),
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        try:
            resolved = self.filing_resolver.resolve(parsed)
        except ValueError as exc:
            status = "unsupported_request" if "Unsupported filing type" in str(exc) else "clarification_required"
            return AnswerResponse(
                status=status,
                question=question,
                answer=None,
                refusal_reason=str(exc),
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        if self.retriever is None:
            return AnswerResponse(
                status="processing_error",
                question=question,
                answer=None,
                refusal_reason="No retriever configured.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        try:
            try:
                evidence = self.retriever.search(
                    parsed.underlying_question or parsed.original_question,
                    filing_scope=resolved.filing_id,
                )
            except TypeError:
                evidence = self.retriever.search(parsed.underlying_question or parsed.original_question)
        except ApplicationError:
            return AnswerResponse(
                status="insufficient_evidence",
                question=question,
                answer=None,
                refusal_reason="The filing index returned no usable evidence.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        evidence = self._coerce_evidence(evidence)
        if not evidence:
            return AnswerResponse(
                status="insufficient_evidence",
                question=question,
                answer=None,
                refusal_reason="No relevant evidence was found for the selected filing.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        if self.relevance_threshold is not None and float(evidence[0].get("score") or 0.0) < self.relevance_threshold:
            return AnswerResponse(
                status="insufficient_evidence",
                question=question,
                answer=None,
                refusal_reason="Retrieved evidence did not meet the relevance threshold.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        records = self._to_records(evidence)
        prompt = self.prompt_builder.build(parsed, records)
        generated = self.generation_provider.generate(prompt)
        labels = [f"S{index}" for index in range(1, len(evidence) + 1)]
        mapping = dict(zip(labels, evidence, strict=True))
        citation_labels = {match.group(1) for match in re.finditer(r"\[(S\d+)\]", generated)}
        citations = []
        for label in labels:
            if label not in citation_labels:
                continue
            record = mapping[label]
            chunk = record.get("chunk")
            metadata = record.get("metadata")
            citations.append(
                CitationRecord(
                    label=label,
                    chunk_id=str(record.get("chunk_id") or ""),
                    company=getattr(metadata, "company", None) if metadata is not None else None,
                    ticker=getattr(metadata, "ticker", None) if metadata is not None else None,
                    form_type=getattr(metadata, "form_type", None) if metadata is not None else None,
                    filing_period=getattr(metadata, "period_of_report", None) if metadata is not None else None,
                    section=getattr(metadata, "section", None) if metadata is not None else None,
                    source_url=getattr(metadata, "source_url", None) if metadata is not None else None,
                    accession_number=getattr(metadata, "accession_number", None) if metadata is not None else None,
                    excerpt=(chunk.content if chunk is not None else None),
                )
            )

        if not citations:
            return AnswerResponse(
                status="insufficient_evidence",
                question=question,
                answer=None,
                refusal_reason="The generated response did not include valid evidence citations.",
                model_id=getattr(self.generation_provider, "model_name", None),
                prompt_version=self.prompt_version,
            )

        return AnswerResponse(
            status="answered",
            question=question,
            answer=generated,
            citations=tuple(citations),
            refusal_reason=None,
            model_id=getattr(self.generation_provider, "model_name", None),
            prompt_version=self.prompt_version,
        )
