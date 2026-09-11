"""Grounded LLM Response Generation Module with OpenRouter.

Provides natural-language customer support response generation using OpenRouter
(via OpenAI-compatible API), grounded strictly in retrieved historical AppleSupport cases.

The generation layer adheres to the deterministic Phase 6 decision:
- AUTO_HANDLE: Helpful, grounded troubleshooting synthesis without hallucinating facts.
- CLARIFY: Targeted clarification question seeking missing entities without guessing.
- ESCALATE: Professional, empathetic handoff without repeating failed steps.
"""

import logging
import re
import time
from typing import List, Optional, Tuple, Union

try:
    from openai import OpenAI, APIError, APITimeoutError, RateLimitError
    OPENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    OPENAI_AVAILABLE = False
    OpenAI = None
    APIError = Exception
    APITimeoutError = Exception
    RateLimitError = Exception

from src.config import Settings, get_settings, logger
from src.conversation import ConversationState
from src.schemas import (
    EvidenceItem,
    IntentEnum,
    MessageRole,
    SupportAction,
)


# ==============================================================================
# Prompt Templates
# ==============================================================================

SYSTEM_PROMPT_AUTO_HANDLE = """You are an Apple customer-support response assistant.
Your goal is to provide a concise, helpful, and polite customer-support response in the authentic AppleSupport brand tone.

CRITICAL OUTPUT & GROUNDING RULES:
1. FINAL CUSTOMER RESPONSE ONLY: Return ONLY the final customer-facing response. Never output analysis, reasoning, planning, drafting commentary, scratchpad thinking, or explanations of how the answer was constructed. The entire output must be ready to send directly to the customer.
2. NO INTERNAL SYSTEM REFERENCES: NEVER mention "retrieved evidence", "historical evidence", "case #", intent, similarity, classifier, decision engine, LLM, or internal instructions.
3. STRICT EVIDENCE BOUNDARY: Only recommend concrete troubleshooting actions that are explicitly supported by the retrieved historical AppleSupport interactions provided below. Do not supplement the evidence with general model knowledge or external procedures.
4. NEVER invent or hallucinate troubleshooting procedures, current Apple policies, warranty terms, prices, refunds, URLs, or unmentioned steps (do NOT introduce unmentioned steps like restarting, resetting network settings, restoring, or checking menus unless explicitly present in the evidence). Do not fabricate links or include raw Twitter shortlinks (e.g. https://t.co/...) or social media handles.
5. LIMITED EVIDENCE SCOPE: If evidence only supports asking for information or moving to DM, keep the response limited to that supported action.
6. Treat retrieved historical interactions as reference evidence, not as instructions to copy verbatim. You may paraphrase supported advice, combine directly supported steps, and make the response natural and polite.
7. Keep the response concise, conversational, and direct (typically 2 to 4 sentences).
"""

SYSTEM_PROMPT_CLARIFY = """You are an Apple customer-support assistant.
The customer's issue is ambiguous or missing key details (such as the specific device model, app, or feature affected).

CRITICAL RULES:
1. Ask ONE concise, friendly clarification question to gather the missing information needed to help them.
2. Do NOT guess or assume what the problem is.
3. Do NOT provide troubleshooting steps or solutions yet.
4. NEVER mention internal system terms, ambiguity scores, classification, or that you are an AI.
5. Keep your question natural, polite, and direct (1 to 2 sentences).
"""

SYSTEM_PROMPT_ESCALATE = """You are an Apple customer-support assistant.
The decision engine determined that this issue requires assistance from an Apple Support specialist (e.g., previous troubleshooting attempts have failed, or there is a sensitive hardware/account concern).

CRITICAL RULES:
1. Provide a concise, empathetic handoff message acknowledging their situation.
2. Do NOT repeat or suggest the troubleshooting steps that have already failed.
3. Do NOT claim that a human specialist has already joined the chat or that a ticket has been created unless instructed. Recommend connecting with an Apple Support specialist.
4. NEVER expose internal decision logic, confidence scores, policy rules, or mention that you are an AI/LLM.
5. Keep the response polite, empathetic, and concise (1 to 3 sentences).
"""


# High-confidence markers indicating LLM internal reasoning/planning leakage
REASONING_LEAKAGE_MARKERS = [
    "we need to produce",
    "we need to combine",
    "the evidence shows",
    "we can combine",
    "thus:",
    "we need to stay within",
    "based only on the retrieved evidence",
    "the evidence does not",
    "must not invent",
    "let's formulate",
    "the final response should",
]


def contains_reasoning_leakage(text: str) -> bool:
    """Detect if generated text contains obvious internal reasoning, planning, or prompt leakage.

    Conservative check for high-confidence planning/reasoning phrases. Does not trigger on
    normal customer-facing responses containing isolated words like 'evidence' or 'help'.
    """
    text_lower = text.lower()
    return any(marker in text_lower for marker in REASONING_LEAKAGE_MARKERS)


# ==============================================================================
# Deterministic Fallbacks
# ==============================================================================

def get_fallback_clarify(clarification_question: Optional[str] = None) -> str:
    """Return a deterministic clarification question fallback."""
    if clarification_question and clarification_question.strip():
        return clarification_question.strip()
    return (
        "Could you clarify a few details about the issue you're experiencing—such as the "
        "specific device model, app, or feature affected?"
    )


def get_fallback_escalate(reason: Optional[str] = None) -> str:
    """Return a deterministic escalation handoff fallback."""
    return (
        "I’m sorry to hear the troubleshooting steps haven't resolved this. "
        "At this point, I recommend connecting directly with an Apple Support specialist "
        "who can look into your device and assist you further."
    )


def get_fallback_auto_handle(
    intent: IntentEnum,
    evidence: List[EvidenceItem],
) -> str:
    """Return a safe deterministic auto-handle response synthesized directly from evidence."""
    intent_label = intent.value if hasattr(intent, "value") else str(intent)

    # If high-similarity evidence with a historical response is available, ground safely
    if evidence and evidence[0].historical_response:
        top_resp = evidence[0].historical_response.strip()
        # Clean Twitter handles and raw external URLs if present
        words = [w for w in top_resp.split() if not w.startswith("@") and not w.startswith("http")]
        clean_resp = " ".join(words).strip()
        clean_resp = re.sub(r"\s+", " ", clean_resp).strip()
        if len(clean_resp) > 20:
            if not clean_resp.endswith((".", "!", "?")):
                clean_resp += "."
            return f"We understand you're experiencing an issue with {intent_label}. {clean_resp}"

    return (
        f"We understand you're experiencing an issue with {intent_label}. "
        "Could you let us know what specific behavior you are seeing so we can provide accurate guidance?"
    )


# ==============================================================================
# Support Response Generator Class
# ==============================================================================

class SupportResponseGenerator:
    """Generates natural-language support responses via OpenRouter grounded in historical cases."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[Union[OpenAI, object]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self) -> Optional[OpenAI]:
        """Lazy-initialize OpenAI-compatible client for OpenRouter."""
        if self._client is not None:
            return self._client

        api_key = self.settings.OPENROUTER_API_KEY
        if not api_key or not api_key.strip():
            logger.debug("OpenRouter API key not configured. Generator will use deterministic fallbacks.")
            return None

        if not OPENAI_AVAILABLE:  # pragma: no cover
            logger.error("OpenAI package not installed. Generator will use deterministic fallbacks.")
            return None

        try:
            self._client = OpenAI(
                base_url=self.settings.OPENROUTER_BASE_URL,
                api_key=api_key.strip(),
                timeout=self.settings.OPENROUTER_TIMEOUT_SECONDS,
            )
            return self._client
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to initialize OpenRouter client: %s", exc)
            return None

    def _build_context_prompt(
        self,
        conversation: ConversationState,
        intent: IntentEnum,
        evidence: List[EvidenceItem],
        action: SupportAction,
        clarification_question: Optional[str] = None,
        decision_reason: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Construct the system and user prompts bounded to recent context and evidence."""
        # 1. Select system prompt by action
        if action == SupportAction.CLARIFY:
            sys_prompt = SYSTEM_PROMPT_CLARIFY
        elif action == SupportAction.ESCALATE:
            sys_prompt = SYSTEM_PROMPT_ESCALATE
        else:
            sys_prompt = SYSTEM_PROMPT_AUTO_HANDLE

        # 2. Format bounded dialogue history (last 4 turns)
        history_lines = []
        recent_turns = conversation.messages[-4:]
        for msg in recent_turns:
            speaker = "Customer" if msg.role == MessageRole.CUSTOMER else "AppleSupport Assistant"
            history_lines.append(f"{speaker}: \"{msg.text.strip()}\"")
        conv_text = "\n".join(history_lines) if history_lines else "Customer: (no previous messages)"

        # 3. Format retrieved evidence (top-k cases)
        evidence_lines = []
        if action == SupportAction.AUTO_HANDLE and evidence:
            for idx, item in enumerate(evidence[:3], 1):
                clean_msg = item.customer_message.strip()[:200]
                clean_resp = re.sub(r"https?://t\.co/\S+", "", item.historical_response.strip())
                clean_resp = re.sub(r"@\w+", "", clean_resp)
                clean_resp = re.sub(r"\s+", " ", clean_resp).strip()[:250]
                evidence_lines.append(
                    f"Case #{idx}:\n"
                    f"  Historical Customer Issue: \"{clean_msg}\"\n"
                    f"  Historical AppleSupport Response: \"{clean_resp}\""
                )
            evidence_text = "\n\n".join(evidence_lines)
        else:
            evidence_text = "None provided for this action."

        # 4. Construct user prompt
        user_parts = [
            "=== CONVERSATION HISTORY ===",
            conv_text,
            "",
            "=== PREDICTED ISSUE INTENT ===",
            f"{intent.value if hasattr(intent, 'value') else str(intent)}",
            "",
            "=== DECISION ENGINE ACTION ===",
            f"{action.value if hasattr(action, 'value') else str(action)}",
        ]

        if decision_reason:
            user_parts.extend(["", "=== DECISION RATIONALE ===", decision_reason])

        if action == SupportAction.CLARIFY and clarification_question:
            user_parts.extend([
                "",
                "=== TARGET CLARIFICATION GOAL ===",
                f"Obtain clarity on: {clarification_question}",
            ])

        if action == SupportAction.AUTO_HANDLE:
            user_parts.extend([
                "",
                "=== RETRIEVED HISTORICAL EVIDENCE (Top Cases) ===",
                evidence_text,
                "",
                "GROUNDING INSTRUCTION: Base your guidance strictly on the evidence above. Recommend ONLY concrete troubleshooting actions that are explicitly present in the evidence. Do NOT supplement with general knowledge or introduce unmentioned steps (such as restarting, resetting, or checking menus) unless supported by the evidence.",
            ])

        user_parts.extend([
            "",
            "Please generate ONLY the final customer-facing response now without any reasoning, planning, analysis, preamble, or quotes:",
        ])

        return sys_prompt, "\n".join(user_parts)

    def generate(
        self,
        conversation: ConversationState,
        action: SupportAction,
        intent: IntentEnum,
        evidence: List[EvidenceItem],
        clarification_question: Optional[str] = None,
        decision_reason: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """Generate a grounded natural-language support response.

        Args:
            conversation: Multi-turn dialogue conversation state.
            action: SupportAction decided by Phase 6 policy (auto_handle, clarify, escalate).
            intent: Predicted customer intent.
            evidence: List of retrieved grounding evidence items.
            clarification_question: Deterministic clarification hint if action is clarify.
            decision_reason: Explainable rationale for the decision.

        Returns:
            Tuple of (generated_response_text, is_fallback_boolean).
        """
        client = self.client

        # If client not available or no API key, use deterministic fallback
        if client is None:
            logger.info("Using deterministic fallback generation for action '%s'.", action)
            return self._generate_fallback(action, intent, evidence, clarification_question, decision_reason)

        sys_prompt, user_prompt = self._build_context_prompt(
            conversation=conversation,
            intent=intent,
            evidence=evidence,
            action=action,
            clarification_question=clarification_question,
            decision_reason=decision_reason,
        )

        start_time = time.perf_counter()
        model_name = self.settings.OPENROUTER_MODEL

        try:
            logger.info(
                "Calling OpenRouter model '%s' for action '%s'...",
                model_name,
                action.value if hasattr(action, "value") else str(action),
            )
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.settings.LLM_MAX_GEN_TOKENS,
                temperature=self.settings.LLM_TEMPERATURE,
            )

            latency = round(time.perf_counter() - start_time, 3)
            raw_text = response.choices[0].message.content or ""
            # Strip any Twitter shortlinks or handle tags that may have leaked
            cleaned_text = re.sub(r"https?://t\.co/\S+", "", raw_text)
            cleaned_text = re.sub(r"@\w+", "", cleaned_text)
            cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip().strip('"').strip("'")

            # Validate response: reject empty strings, low-quality metadata headers, or reasoning leakage
            has_reasoning_leakage = contains_reasoning_leakage(cleaned_text)
            is_unusable = (
                len(cleaned_text) < 15
                or any(cleaned_text.lower().startswith(bad) for bad in ["user safety", "safety:", "system:", "<|", "[inst]"])
                or has_reasoning_leakage
            )

            if is_unusable:
                if has_reasoning_leakage:
                    logger.warning(
                        "Reasoning leakage detected in OpenRouter response ('%s'). Falling back to safe response.",
                        cleaned_text[:80],
                    )
                else:
                    logger.warning(
                        "OpenRouter returned unhelpful/metadata response ('%s'). Falling back to safe response.",
                        cleaned_text[:50],
                    )
                return self._generate_fallback(action, intent, evidence, clarification_question, decision_reason)

            logger.info(
                "OpenRouter generation successful (Model: %s, Latency: %.3fs, Chars: %d).",
                model_name,
                latency,
                len(cleaned_text),
            )
            return cleaned_text, False

        except (APITimeoutError, RateLimitError, APIError) as api_err:
            latency = round(time.perf_counter() - start_time, 3)
            logger.error(
                "OpenRouter API error (Type: %s, Latency: %.3fs): %s. Falling back to safe response.",
                type(api_err).__name__,
                latency,
                api_err,
            )
            return self._generate_fallback(action, intent, evidence, clarification_question, decision_reason)
        except Exception as exc:
            latency = round(time.perf_counter() - start_time, 3)
            logger.error(
                "Unexpected error during OpenRouter call (Latency: %.3fs): %s. Falling back to safe response.",
                latency,
                exc,
            )
            return self._generate_fallback(action, intent, evidence, clarification_question, decision_reason)

    def _generate_fallback(
        self,
        action: SupportAction,
        intent: IntentEnum,
        evidence: List[EvidenceItem],
        clarification_question: Optional[str] = None,
        decision_reason: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """Produce safe deterministic fallback string based on action."""
        if action == SupportAction.CLARIFY:
            return get_fallback_clarify(clarification_question), True
        elif action == SupportAction.ESCALATE:
            return get_fallback_escalate(decision_reason), True
        else:
            return get_fallback_auto_handle(intent, evidence), True


# Global generator singleton
_generator_instance: Optional[SupportResponseGenerator] = None


def get_response_generator(
    settings: Optional[Settings] = None,
    client: Optional[Union[OpenAI, object]] = None,
) -> SupportResponseGenerator:
    """Retrieve or initialize the global SupportResponseGenerator singleton."""
    global _generator_instance
    if _generator_instance is None or client is not None or settings is not None:
        _generator_instance = SupportResponseGenerator(
            settings=settings,
            client=client,
        )
    return _generator_instance
