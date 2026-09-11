"""Conversation-Aware Support Decision Agent for AppleSupport.

Orchestrates multi-turn dialogue context tracking, supervised intent classification,
dense semantic retrieval, explainable signal analysis, and policy action selection.
"""

from typing import Optional, Union

from src.classifier import IntentClassifier, get_classifier
from src.config import Settings, get_settings, logger
from src.conversation import ConversationState
from src.escalation import evaluate_decision_policy
from src.generator import SupportResponseGenerator, get_response_generator
from src.retriever import BaseRetriever, get_retriever, get_semantic_retriever
from src.schemas import (
    AgentRequest,
    AgentResponse,
    DecisionSignals,
    IntentEnum,
    RetrievalSummary,
    SupportAction,
)


class SupportDecisionAgent:
    """Conversation-aware decision engine selecting AUTO_HANDLE, CLARIFY, or ESCALATE."""

    def __init__(
        self,
        classifier: Optional[IntentClassifier] = None,
        retriever: Optional[BaseRetriever] = None,
        generator: Optional[SupportResponseGenerator] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.classifier = classifier or get_classifier()
        self.retriever = retriever or get_semantic_retriever() or get_retriever()
        self.generator = generator or get_response_generator(settings=self.settings)

    def process(self, request_or_conv: Union[AgentRequest, ConversationState]) -> AgentResponse:
        """Process an incoming conversation request and return an actionable decision.

        Args:
            request_or_conv: AgentRequest Pydantic model or ConversationState instance.

        Returns:
            Structured AgentResponse containing action, intent, confidence, reasons, and signals.
        """
        if isinstance(request_or_conv, AgentRequest):
            conv = ConversationState(
                conversation_id=request_or_conv.conversation_id,
                messages=request_or_conv.messages,
            )
        else:
            conv = request_or_conv

        latest_cust_msg = conv.latest_customer_message.text.strip()
        effective_query = conv.get_effective_query()

        logger.info(
            "Processing conversation '%s' (Turns: %d, Effective Query: '%s')...",
            conv.conversation_id,
            conv.turns_count,
            effective_query[:60],
        )

        # 1. Intent Classification (using effective dialogue query)
        if not self.classifier or not self.classifier.is_trained:
            logger.warning("Classifier not loaded. Using fallback intent.")
            predicted_intent = IntentEnum.OTHER_GENERAL
            intent_confidence = 0.50
        else:
            cls_response = self.classifier.classify(effective_query)
            predicted_intent = cls_response.intent
            intent_confidence = float(cls_response.confidence)

        # 2. Semantic Retrieval Grounding
        evidence_items = []
        if not self.retriever or not self.retriever.is_fitted:
            logger.warning("Retriever not loaded. Zero evidence available.")
        else:
            evidence_items = self.retriever.retrieve(
                effective_query,
                top_k=self.settings.TOP_K_RETRIEVAL,
            )

        top_sim = float(evidence_items[0].similarity) if evidence_items else 0.0

        # 3. Decision Policy Evaluation
        (
            action,
            reason,
            clarification_question,
            is_ambiguous,
            evidence_sufficient,
            repeated_troubleshoot,
            is_frustrated,
            is_resolved_closing,
        ) = evaluate_decision_policy(
            conversation=conv,
            predicted_intent=predicted_intent,
            intent_confidence=intent_confidence,
            evidence_items=evidence_items,
            settings=self.settings,
        )

        # 4. Grounded Response Generation (Phase 7)
        response_text, is_fallback = self.generator.generate(
            conversation=conv,
            action=action,
            intent=predicted_intent,
            evidence=evidence_items,
            clarification_question=clarification_question,
            decision_reason=reason,
        )

        # For clarify, align clarification_question with response if applicable
        if action == SupportAction.CLARIFY and not clarification_question:
            clarification_question = response_text
        elif action == SupportAction.ESCALATE:
            clarification_question = None

        return AgentResponse(
            conversation_id=conv.conversation_id,
            action=action,
            intent=predicted_intent,
            intent_confidence=intent_confidence,
            reason=reason,
            response=response_text,
            clarification_question=clarification_question,
            retrieval=RetrievalSummary(
                top_similarity=round(top_sim, 4),
                top_k=len(evidence_items),
            ),
            signals=DecisionSignals(
                ambiguous=is_ambiguous,
                evidence_sufficient=evidence_sufficient,
                repeated_troubleshooting=repeated_troubleshoot,
                frustrated=is_frustrated,
                resolved_closing=is_resolved_closing,
            ),
            evidence=evidence_items,
        )


# Global singleton agent instance
_agent_instance: Optional[SupportDecisionAgent] = None


def get_support_agent(
    classifier: Optional[IntentClassifier] = None,
    retriever: Optional[BaseRetriever] = None,
    generator: Optional[SupportResponseGenerator] = None,
    settings: Optional[Settings] = None,
) -> SupportDecisionAgent:
    """Retrieve or initialize the global SupportDecisionAgent singleton."""
    global _agent_instance
    if _agent_instance is None or classifier is not None or retriever is not None or generator is not None:
        _agent_instance = SupportDecisionAgent(
            classifier=classifier,
            retriever=retriever,
            generator=generator,
            settings=settings,
        )
    return _agent_instance
