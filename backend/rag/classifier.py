"""Document classification: loan vs scheme (one LLM call over the title and
first ~2 pages), in the same DSPy style as supervisor.agent.ClassifyDomain."""

from typing import Literal

import dspy
from pydantic import BaseModel

from rag.extract import Page
from workers.base_worker import build_fast_lm


class ClassifyDocument(dspy.Signature):
    """Decide whether this document describes a LOAN product (borrowing money
    from a bank or lender) or a government/bank SCHEME (a savings, pension,
    subsidy or welfare scheme). Answer "unclear" if the excerpt does not make
    it obvious -- do not guess. confidence is 0.0-1.0."""

    filename: str = dspy.InputField()
    excerpt: str = dspy.InputField(desc="Title and first pages of the document.")
    doc_type: Literal["loan", "scheme", "unclear"] = dspy.OutputField()
    confidence: float = dspy.OutputField()
    suggested_name: str = dspy.OutputField(desc="Short human-readable name of the product.")


class Classification(BaseModel):
    doc_type: Literal["loan", "scheme", "unclear"]
    confidence: float
    suggested_name: str = ""


_classify = dspy.Predict(ClassifyDocument)
_EXCERPT_CHARS = 5000


def classify_document(filename: str, pages: list[Page]) -> Classification:
    excerpt = "\n\n".join(p.text for p in pages[:2])[:_EXCERPT_CHARS]
    if not excerpt.strip():
        return Classification(doc_type="unclear", confidence=0.0)
    try:
        with dspy.context(lm=build_fast_lm()):
            prediction = _classify(filename=filename, excerpt=excerpt)
        return Classification(
            doc_type=prediction.doc_type,
            confidence=max(0.0, min(1.0, float(prediction.confidence))),
            suggested_name=str(prediction.suggested_name or ""),
        )
    except Exception:
        # An LLM outage must not auto-publish a document: send it to review.
        return Classification(doc_type="unclear", confidence=0.0)
