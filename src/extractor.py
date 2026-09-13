"""Structured extraction via an LLM (Groq by default) using Instructor.

Also tracks token usage / estimated cost per domain (bonus requirement).
"""
from __future__ import annotations

import os
from importlib import import_module

from groq import Groq

from .models import LeadEnrichmentResult

# Load the optional integration dynamically so environments that do not include
# the package do not report a static unresolved import for this module.
instructor = import_module("instructor")

SYSTEM_PROMPT = (
    "You are a precise B2B research analyst. You will be given cleaned "
    "markdown scraped from a company's public website (homepage + subpages "
    "like /about, /team, /contact, /pricing). Extract only information that "
    "is explicitly present in the text. Do not invent names, emails, or "
    "URLs. If something isn't present, leave the field empty or omit it. "
    "Set data_confidence_score lower when key fields (team, contact, ICP) "
    "are missing or ambiguous."
)


class LLMExtractor:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = instructor.from_groq(
            Groq(api_key=api_key or os.getenv("GROQ_API_KEY")),
            mode=instructor.Mode.TOOLS,
        )
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.price_per_1m_input = float(os.getenv("PRICE_PER_1M_INPUT", "0.59"))
        self.price_per_1m_output = float(os.getenv("PRICE_PER_1M_OUTPUT", "0.79"))
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def extract(self, domain: str, context: str) -> tuple[LeadEnrichmentResult, dict]:
        """Returns (result, usage_info). usage_info includes tokens + est. cost."""
        result, completion = self.client.chat.completions.create_with_completion(
            model=self.model,
            response_model=LeadEnrichmentResult,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Domain: {domain}\n\nScraped content:\n{context}\n\n"
                        "Extract the structured lead enrichment data."
                    ),
                },
            ],
            max_retries=2,
        )

        usage = getattr(completion, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        est_cost = (
            input_tokens / 1_000_000 * self.price_per_1m_input
            + output_tokens / 1_000_000 * self.price_per_1m_output
        )

        result.domain = domain
        usage_info = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(est_cost, 6),
        }
        return result, usage_info