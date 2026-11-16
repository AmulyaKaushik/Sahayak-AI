"""Refiner: turns structured agent outputs into voice-friendly text.

May reword, never change a fact. Same philosophy as workers/narration_guard:
after the LLM rewrites, verify the verdicts and every number survived; if
not, use the deterministic template instead.

The LLM is only used when it earns its cost: a non-English reply (needs
translation). English replies are already plain sentences (templated
eligibility text, RAG answers written as complete sentences), so they get the
deterministic cleanup only."""

import asyncio
import logging
import re

import dspy

from sahayak_ai.models import AgentOutput, Refined
from workers.base_worker import build_fast_lm
from eligibility_agent.agent import EligibilityOutput
from supervisor.agent import FIELD_PROMPTS
from workers.friendly import friendly_text, join_natural, requirement_label, scheme_name
from workers.narration_guard import narration_contradicts_verdict

logger = logging.getLogger(__name__)

NO_ANSWER_TEXT = "I could not find that in the official documents I have. Please ask a bank officer."
UNAVAILABLE_TEXT = (
    "I am having trouble looking that up right now. Please try again in a minute."
)

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class RefineForSpeech(dspy.Signature):
    """Rewrite the facts as a short spoken reply for a voice assistant. Use
    at most 3 short sentences, no markdown, bullets or symbols, say "rupees"
    instead of Rs, and end with ONE clear next step if the facts ask the
    customer for something. Keep every number as ASCII digits and keep every
    eligible / not eligible verdict exactly as given. Add no new facts. Reply
    in the language named by language_tag. Never guess what a number or
    fact refers to and never turn it into a statement about the customer
    themselves unless the facts say so. The assistant cannot contact anyone,
    book anything or do anything outside this chat, so never say or imply it
    will; where the facts say to ask a bank officer, tell the customer to
    ask one. When some facts answer the question and others say the answer
    was not found, give the answer and then say plainly which part was not
    found in the documents."""

    facts: str = dspy.InputField()
    language_tag: str = dspy.InputField(desc="BCP-47 tag, e.g. hi-IN or en-IN.")
    speech_text: str = dspy.OutputField()


_refine = dspy.Predict(RefineForSpeech)


def humanize(text: str) -> str:
    """Deterministic cleanup so TTS doesn't read symbols or identifiers."""
    # "₹1,000," -> "1,000 rupees,"; "Rs 1.2 lakh" -> "1.2 lakh rupees".
    text = re.sub(
        r"(?:Rs\.?|INR|₹)\s*(\d+(?:,\d+)*(?:\.\d+)?)(\s+(?:lakhs?|crores?|thousand|million))?",
        lambda m: m.group(1) + (m.group(2) or "") + " rupees",
        text,
    )
    text = friendly_text(text.replace("Based on our records, ", ""))
    text = re.sub(r"[*#`_>]+", lambda m: " " if "_" in m.group() else "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def _source_line(output: AgentOutput) -> str:
    if not output.rag or not output.rag.sources:
        return ""
    names = ", ".join(
        f"{s.doc}" + (f" p.{s.page}" if s.page else "") for s in output.rag.sources
    )
    return f"(Source: {names})"


def _ask_line(others: list, brief: bool) -> str:
    """One short request for what is still needed, not one per scheme."""
    if brief:
        for result in others:
            if result.ask:
                fields = result.ask[:2]
                prompts = join_natural([FIELD_PROMPTS.get(f, f) for f in fields])
                return f"For {scheme_name(result.scheme_id)}, please tell me {prompts}."
        return ""
    counts: dict[str, int] = {}
    for result in others:
        for field in result.ask:
            counts[field] = counts.get(field, 0) + 1
    if not counts:
        return ""
    top = sorted(counts, key=lambda f: -counts[f])[:2]
    return "To check more, please tell me " + join_natural([FIELD_PROMPTS.get(f, f) for f in top]) + "."


def summarize_eligibility(output: EligibilityOutput) -> str | None:
    """Short reply for a multi-scheme answer or a fact the customer just
    stated: who they qualify for, the closest ones, how many are left, and ONE
    thing to ask. The full per-scheme detail stays in the response's results.
    None = keep the normal single-scheme sentence."""
    results = output.results
    brief = output.turn_type == "recheck_unresolved"
    if not results or (len(results) == 1 and not brief):
        return None

    eligible = [r for r in results if r.eligible]
    others = sorted((r for r in results if not r.eligible), key=lambda r: len(r.missing))
    parts = ["Got it, I've noted that."] if brief else []
    if eligible:
        parts.append(f"You are eligible for {join_natural([scheme_name(r.scheme_id) for r in eligible])}.")
    if not brief:
        close = [r for r in others if len(r.missing) <= 2][:2]
        for index, r in enumerate(close):
            lead = "You are close on" if index == 0 else "You are also close on"
            needs = join_natural([requirement_label(m) for m in r.missing])
            parts.append(f"{lead} {scheme_name(r.scheme_id)}, which still needs {needs}.")
        rest = len(others) - len(close)
        if rest > 0:
            if not eligible and not close:
                parts.append(f"You are not eligible for any of the {len(results)} yet.")
            else:
                parts.append(f"You are not eligible yet for {rest} other{'s' if rest > 1 else ''}.")
    ask = _ask_line(others, brief)
    if ask:
        parts.append(ask)
    return " ".join(parts)


def _plain_parts(outputs: list[AgentOutput]) -> list[str]:
    parts = []
    for output in outputs:
        if output.eligibility:
            parts.append(summarize_eligibility(output.eligibility) or output.eligibility.reply_text)
        elif output.rag:
            parts.append(
                output.rag.answer or (UNAVAILABLE_TEXT if output.rag.unavailable else NO_ANSWER_TEXT)
            )
    return [p for p in parts if p]


def deterministic(outputs: list[AgentOutput]) -> Refined:
    parts = [friendly_text(p) for p in _plain_parts(outputs)]
    sources = " ".join(s for s in (_source_line(o) for o in outputs) if s)
    display = " ".join(parts) + (f" {sources}" if sources else "")
    return Refined(speech_text=humanize(" ".join(parts)), display_text=display.strip())


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def _preserves_facts(candidate: str, base: str, outputs: list[AgentOutput], language: str) -> bool:
    if not candidate.strip() or not _numbers(base) <= _numbers(candidate):
        return False
    if language.lower().startswith("en"):
        for output in outputs:
            if output.eligibility and len(output.eligibility.results) == 1:
                if narration_contradicts_verdict(candidate, output.eligibility.results[0].eligible):
                    return False
    return True


def _needs_llm(outputs: list[AgentOutput], language: str) -> bool:
    # English replies are already plain sentences (templated eligibility text,
    # RAG answers written as 1-3 complete sentences), so only humanize() runs.
    # The LLM is needed only to translate.
    return not language.lower().startswith("en")


def _refine_sync(facts: str, language: str) -> str:
    with dspy.context(lm=build_fast_lm()):
        return _refine(facts=facts, language_tag=language).speech_text


async def refine(outputs: list[AgentOutput], language: str = "en-IN") -> Refined:
    base = deterministic(outputs)
    if not _needs_llm(outputs, language) or not base.speech_text:
        return base

    try:
        candidate = (await asyncio.to_thread(_refine_sync, base.speech_text, language)).strip()
    except Exception:
        logger.warning("Refiner: LLM rewrite failed; using the plain text", exc_info=True)
        return base

    if not _preserves_facts(candidate, base.speech_text, outputs, language):
        return base
    return Refined(speech_text=humanize(candidate), display_text=base.display_text)
