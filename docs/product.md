# AskMyDocs AI — Product Document

## 1. Product Overview

AskMyDocs AI is an evidence-grounded RAG system for analysing public-company SEC filings.

Users can ask natural-language questions about company 10-K and 10-Q filings and receive answers grounded in the actual filing content, with citations pointing back to the relevant source sections.

The project is designed to demonstrate strong fundamentals in:

- Retrieval-Augmented Generation
- document ingestion and parsing
- semantic and sparse retrieval
- hybrid retrieval
- reranking
- grounding and citation validation
- evaluation
- AI application architecture
- deployment

The project is learning-focused rather than a commercial financial product.

---

## 2. Product Vision

Make information contained in long SEC filings easier to access by allowing users to ask natural-language questions and receive concise, evidence-backed answers without manually searching through hundreds of pages.

The system should demonstrate that a well-designed retrieval pipeline can produce reliable answers without depending on expensive frontier models.

---

## 3. Problem Statement

SEC filings contain large amounts of valuable information about public companies, including:

- business performance
- risk factors
- revenue and expenses
- management discussion
- regulatory risks
- strategic priorities
- operational information
- financial disclosures
- notes and tables

These filings are often lengthy and structurally complex.

Traditional keyword search can miss semantically related information, while general-purpose language models may produce answers that are not grounded in the source document.

A basic RAG system can improve grounding, but real SEC filings introduce additional challenges:

- long documents
- section structure
- tables
- footnotes
- repeated terminology
- cross-references
- numerical information
- precise citation requirements

AskMyDocs AI focuses on solving these retrieval and grounding problems.

---

## 4. Core Product Principle

### Retrieval quality over model size

The project prioritizes:

1. document quality;
2. chunking quality;
3. retrieval quality;
4. reranking;
5. grounding and citation validation;
6. generation quality.

A larger or more expensive generation model should not be used as a substitute for poor retrieval.

Model selection must be based on measurable evaluation results.

---

## 5. Target Users

The project is primarily designed for:

### Financial researchers

Users who need to locate specific facts or disclosures inside lengthy SEC filings.

### Students and researchers

Users who want to explore company filings without manually reading entire documents.

### Technical users

Developers and engineers interested in understanding how a complete RAG system works.

The application is not intended to provide professional investment advice.

---

## 6. Primary User Experience

The primary interaction should be simple:

```text
User asks a question
        ↓
System identifies the relevant company and filing
        ↓
System obtains the filing if necessary
        ↓
System retrieves relevant evidence
        ↓
System reranks the evidence
        ↓
System generates an answer
        ↓
System validates the answer against evidence
        ↓
User receives answer + citations