"""Conversation-aware decision engine policy and diagnostic signal evaluation.

Implements interpretable, multi-signal reasoning across:
1. Sensitive escalation triggers (hardware damage, human requests, legal)
2. Resolved/closing conversation detection (Phase 10)
3. Repeated troubleshooting detection (improved Phase 10 regex)
4. Frustration detection (Phase 10)
5. Ambiguity detection (vague referents, missing products/features)
6. Evidence quality assessment (similarity thresholds, intent consistency)
7. Three-action decision policy: AUTO_HANDLE, CLARIFY, or ESCALATE

Phase 10 Policy Priority Order:
1. ESCALATE: Sensitive/safety issue
2. AUTO_HANDLE: Resolved/closing conversation
3. ESCALATE: Repeated failed troubleshooting
4. ESCALATE: Frustration + unresolved issue
5. CLARIFY: Ambiguous referent
6. CLARIFY: Low intent confidence (changed from ESCALATE in Phase 10)
7. CLARIFY: Insufficient retrieval evidence (changed from ESCALATE in Phase 10)
8. AUTO_HANDLE: Clear intent + sufficient evidence
"""

import re
from typing import List, Optional, Tuple

from src.config import Settings, get_settings, logger
from src.conversation import ConversationState
from src.schemas import EvidenceItem, IntentEnum, SupportAction

# Domain entities and features relevant to AppleSupport
KNOWN_APPLE_ENTITIES = {
    # Hardware & Devices
    "iphone", "ipad", "mac", "macbook", "imac", "apple watch", "watch",
    "airpods", "airpod", "apple tv", "ipod", "display", "screen", "battery",
    "charger", "cable", "charging", "speaker", "microphone", "mic", "camera",
    "touch id", "face id", "button", "keyboard", "trackpad", "headphone", "headphones",
    # Connectivity & Networks
    "wi-fi", "wifi", "bluetooth", "cellular", "lte", "4g", "5g", "airdrop",
    "hotspot", "signal", "service", "carrier", "sim", "esim", "network", "pairing",
    # Operating Systems & Software
    "ios", "macos", "watchos", "tvos", "ipados", "itunes", "safari",
    # Core Apps & Features
    "messages", "imessage", "facetime", "mail", "photos", "photo", "music",
    "apple music", "spotify", "app store", "maps", "notes", "podcasts",
    "wallet", "apple pay", "calendar", "reminders", "youtube", "whatsapp",
    "instagram", "facebook", "twitter", "snapchat", "netflix", "siri", "widget",
    # Accounts & Data
    "apple id", "icloud", "password", "passcode", "account", "login", "sign in",
    "backup", "restore", "storage", "subscription", "purchase", "purchases", "refund",
}

# ---------------------------------------------------------------------------
# Troubleshooting failure indicators (Phase 10 expanded)
# ---------------------------------------------------------------------------
TROUBLESHOOTING_INDICATORS = [
    # Original Phase 6 patterns
    r"\balready\s+(tried|did|done|tested|attempted)\b",
    r"\btried\s+(that|it|this|all|everything)\b",
    r"\bdid\s+(that|it|this)\s+(already|too)\b",
    r"\bdone\s+(that|this)\s+(already|too|multiple\s+times)\b",
    r"\b(still|again)\s+(not|isn't|is\s+not|doesn't|does\s+not|won't)\s+(working|connect|work|charge|responding|turn\s+on)\b",
    r"\bnothing\s+(is\s+)?working\b",
    r"\bmultiple\s+times\b",
    r"\bpersists\b",
    r"\btried\s+(restarting|rebooting|resetting)\b",
    # Phase 10 additions — catch missed Phase 8A cases
    r"\bstill\s+(having|has|have)\s+(problems?|issues?|trouble)\b",  # Gold #2: "Still having problems"
    r"\b(tried|did)\s+(the\s+)?(steps?|instructions?|suggestions?)\b",  # Gold #44: "Tried the steps"
    r"\b(doesn't|does\s+not|didn't|did\s+not)\s+(work|help|fix)\b",  # General: "didn't work"
    r"\bnot\s+working\s+(at\s+all)\b",  # Gold #184: "Not working at all"
    r"\b(still|it\s+still)\s+happen",  # Gold #41: "It still happen"
    r"\bsame\s+(issue|problem|thing)\b",  # "same issue"
    r"\bno\s+(luck|improvement|change)\b",  # "no luck"
    r"\bnot\s+fixed\b",  # "not fixed"
    r"\bstill\s+broken\b",  # "still broken"
    r"\bproblem\s+persists\b",  # "problem persists"
    r"\bthat\s+didn'?t\s+help\b",  # "that didn't help"
    r"\bdm\s+(you|u)\s+several\s+times\b",  # Gold #153: "dm you several times"
]

# Sensitive escalation triggers (hardware damage, physical danger, explicit agent request)
SENSITIVE_TRIGGERS = [
    (r"\b(cracked|shattered|broken\s+glass|water\s+damage|liquid|dropped\s+in\s+water|swollen|smoke|spark|burnt)\b", "Physical hardware damage or hazard requires in-person or hardware specialist inspection."),
    (r"\b(speak|talk|transfer|connect)\s+(to\s+|me\s+to\s+)?(a\s+)?(human|agent|person|representative|support\s+staff)\b", "Customer explicitly requested assistance from a human support specialist."),
    (r"\b(lawyer|attorney|legal|sue|court)\b", "Legal escalation requires human supervisor handling."),
]

# ---------------------------------------------------------------------------
# Resolved/closing conversation patterns (Phase 10)
# ---------------------------------------------------------------------------
RESOLVED_PATTERNS = [
    r"\b(works?\s+now|working\s+now)\b",
    r"\b(problem\s+solved|issue\s+solved|issue\s+resolved)\b",
    r"\b(it'?s?\s+)?fixed\b",
    r"\b(all\s+good|everything\s+(is\s+)?working)\b",
    r"\bfigured\s+(it\s+)?out\b",
    r"\b(it'?s?\s+)?sorted(\s+now)?(\s+out)?\b",
    r"\bcleared\s+up\b",
    r"\bit\s+finally\s+worked\b",
    r"\bhave\s+not\s+had\s+the\s+issue\b",
    r"\bseems?\s+to\s+have\s+(cleared|fixed|resolved)\b",
    r"\bgot\s+it\s+figured\s+out\b",
    r"\bmanaged\s+to\s+(get|fix|resolve|download)\b",
    r"\bgot\s+it\s+(working|fixed|sorted)\b",
]

CLOSING_PATTERNS = [
    r"\b(thank\s*you|thanks|thx|thanku|thnku)\b",
    r"\bappreciate\s+(it|your|the)\b",
    r"\btalked?\s+to\s+(apple\s+)?support\b",
    r"\bgot\s+(on\s+)?a\s+call\b",  # Gold #42: "Managed to get on a call"
    r"\bhappy\s*thanksgiving\b",
]

# ---------------------------------------------------------------------------
# Frustration signal patterns (Phase 10)
# ---------------------------------------------------------------------------
FRUSTRATED_EMOJI_PATTERN = re.compile(r"[\U0001F621\U0001F624\U0001F623\U0001F62B\U0001F92C\U0001F620]")
# 😡 😤 😣 😫 🤬 😠

FRUSTRATION_PHRASES = [
    r"\b(this\s+is\s+)?(ridiculous|unacceptable|disgraceful|absurd|pathetic)\b",
    r"\b(this\s+is\s+)?stupid\b",
    r"\bplease\s+help\b",
    r"\bfucked?\s+(up|it)\b",
    r"\bwaste?\s+(my\s+)?time\b",
    r"\bbeen\s+waiting\b",
    r"\bno\s+response\b",
    r"\bnot\s+responding\b",
]


def detect_ambiguity(conversation: ConversationState) -> Tuple[bool, Optional[str], Optional[str]]:
    """Detect whether the customer inquiry lacks enough information to safely determine the issue.

    Returns:
        Tuple of (is_ambiguous, reason, clarification_question).
    """
    latest_msg = conversation.latest_customer_message.text.strip()
    all_customer_text = conversation.get_full_customer_text().lower()
    latest_lower = latest_msg.lower()

    # 1. Check if any recognized Apple entity, feature, or app exists across the conversation
    has_known_entity = any(entity in all_customer_text for entity in KNOWN_APPLE_ENTITIES)

    # 2. Check for vague referent patterns in the latest customer turn
    vague_pronoun_patterns = [
        r"\b(it|this|that|something)\s+(stopped\s+working|is\s+not\s+working|isn't\s+working|won't\s+work|broke|broken|failed)\b",
        r"\b(stopped\s+working|won't\s+work|isn't\s+working)\s+after\s+(the|my|an|i)?\s*(update|updated)\b",
        r"^(it|this|that)\s+(doesn't|won't|can't)\s+(work|load|open|start)\b",
        r"\bproblem\s+after\s+(the\s+)?update\b",
    ]
    has_vague_referent = any(re.search(pat, latest_lower) for pat in vague_pronoun_patterns)

    # 3. Check for ultra-short vague complaints (< 20 characters with no entity)
    is_ultra_short = len(latest_msg.split()) <= 4 and not has_known_entity

    if (has_vague_referent or is_ultra_short) and not has_known_entity:
        # Determine tailored clarification question based on available context
        if "update" in latest_lower or "updated" in latest_lower:
            question = "Could you clarify what stopped working after the update—for example, Wi-Fi, Messages, an app, or another feature?"
        elif "password" in latest_lower or "login" in latest_lower or "sign in" in latest_lower:
            question = "Could you clarify whether you are having trouble with your Apple ID password, device passcode, or iCloud login?"
        elif "screen" in latest_lower or "display" in latest_lower:
            question = "Could you clarify which device model is affected and whether the screen is black, frozen, or unresponsive to touch?"
        else:
            question = "Could you please clarify which device, app, or feature is experiencing the issue?"

        reason = "The affected product or feature is unclear."
        logger.info("Ambiguity detected: '%s' (Reason: %s)", latest_msg, reason)
        return True, reason, question

    return False, None, None


def detect_repeated_troubleshooting(conversation: ConversationState) -> Tuple[bool, Optional[str]]:
    """Detect if the customer has indicated repeated unsuccessful troubleshooting attempts.

    Phase 10: Expanded regex patterns and single-turn detection for messages
    that contain both a troubleshooting action and a failure report in the same message.

    Returns:
        Tuple of (has_repeated_troubleshooting, reason).
    """
    cust_msgs = conversation.customer_messages
    asst_msgs = conversation.assistant_messages

    troubleshooting_matches = 0

    for msg in cust_msgs:
        text_lower = msg.text.lower()
        for pat in TROUBLESHOOTING_INDICATORS:
            if re.search(pat, text_lower):
                troubleshooting_matches += 1
                break

    # If assistant previously offered troubleshooting advice and customer indicates they already tried it
    if asst_msgs and len(cust_msgs) >= 2:
        latest_cust_lower = cust_msgs[-1].text.lower()
        if any(re.search(pat, latest_cust_lower) for pat in TROUBLESHOOTING_INDICATORS):
            reason = (
                "Previous troubleshooting attempts have failed and further assistance "
                "may require a human support specialist."
            )
            logger.info("Repeated troubleshooting detected via direct follow-up: '%s'", cust_msgs[-1].text)
            return True, reason

    # Phase 10: Even in single-turn, if the customer message itself contains
    # evidence of prior troubleshooting AND continued failure, escalate.
    # e.g., "I reset the phone settings. Still having problems."
    if troubleshooting_matches >= 1:
        latest_cust_lower = cust_msgs[-1].text.lower() if cust_msgs else ""
        # Check if the LATEST message alone has a troubleshooting indicator
        latest_has_indicator = any(re.search(pat, latest_cust_lower) for pat in TROUBLESHOOTING_INDICATORS)
        if latest_has_indicator:
            reason = (
                "Customer reported that troubleshooting steps have not resolved the issue. "
                "Escalating to human support specialist."
            )
            logger.info("Troubleshooting failure detected in customer message: '%s'", cust_msgs[-1].text)
            return True, reason

    # Or if multiple troubleshooting failure statements occur throughout dialogue
    settings = get_settings()
    if troubleshooting_matches >= settings.MAX_TROUBLESHOOTING_ATTEMPTS:
        reason = (
            f"Customer indicated {troubleshooting_matches} unsuccessful troubleshooting attempts; "
            "escalating to human support to avoid repetitive advice."
        )
        logger.info("Repeated troubleshooting threshold reached (%d matches)", troubleshooting_matches)
        return True, reason

    return False, None


def detect_sensitive_escalation(conversation: ConversationState) -> Tuple[bool, Optional[str]]:
    """Detect sensitive scenarios requiring immediate human escalation.

    Returns:
        Tuple of (is_sensitive, reason).
    """
    latest_cust = conversation.latest_customer_message.text.lower()

    for pat, reason in SENSITIVE_TRIGGERS:
        if re.search(pat, latest_cust):
            logger.info("Sensitive escalation triggered: %s", reason)
            return True, reason

    return False, None


def detect_resolved_closing(conversation: ConversationState) -> Tuple[bool, Optional[str]]:
    """Detect if the conversation is resolved or the customer is closing/thanking.

    Phase 10: Prevents unnecessary escalation or clarification when the customer
    indicates the issue is fixed, says thank you, or acknowledges resolution.

    Uses the latest customer message and full conversation context.

    Returns:
        Tuple of (is_resolved_closing, reason).
    """
    latest_msg = conversation.latest_customer_message.text.strip()
    latest_lower = latest_msg.lower()
    all_customer_text = conversation.get_full_customer_text().lower()

    # Check for explicit resolution signals in the latest message
    for pat in RESOLVED_PATTERNS:
        if re.search(pat, latest_lower):
            logger.info("Resolved conversation detected: '%s'", latest_msg[:60])
            return True, "Customer indicated the issue is resolved."

    # Check for closing/thank-you patterns in the latest message
    for pat in CLOSING_PATTERNS:
        if re.search(pat, latest_lower):
            # Only treat as closing if there's no active unresolved complaint
            # in the same message (e.g., "thanks but still broken" should NOT close)
            has_active_complaint = any(
                re.search(p, latest_lower)
                for p in TROUBLESHOOTING_INDICATORS
            )
            if not has_active_complaint:
                logger.info("Closing conversation detected: '%s'", latest_msg[:60])
                return True, "Customer is closing the conversation or expressing gratitude."

    return False, None


def detect_frustration(conversation: ConversationState) -> Tuple[bool, Optional[str]]:
    """Detect frustration or anger signals in the customer's messages.

    Phase 10: Lightweight deterministic frustration detector.
    Frustration alone does NOT trigger escalation — it must be combined
    with an unresolved issue or failed troubleshooting.

    Returns:
        Tuple of (is_frustrated, reason).
    """
    all_customer_text = conversation.get_full_customer_text()
    latest_msg = conversation.latest_customer_message.text.strip()

    reasons = []

    # 1. Angry/frustrated emoji in any customer message
    if FRUSTRATED_EMOJI_PATTERN.search(all_customer_text):
        reasons.append("frustrated emoji detected")

    # 2. Aggressive punctuation (3+ exclamation marks)
    if re.search(r"!{3,}", all_customer_text):
        reasons.append("aggressive punctuation")

    # 3. Frustration phrases
    text_lower = all_customer_text.lower()
    for pat in FRUSTRATION_PHRASES:
        if re.search(pat, text_lower):
            reasons.append("frustration language")
            break

    if reasons:
        reason_str = ", ".join(reasons)
        logger.info("Frustration detected in conversation: %s ('%s')", reason_str, latest_msg[:60])
        return True, f"Customer frustration signals detected ({reason_str})."

    return False, None


def assess_evidence(
    evidence_items: List[EvidenceItem],
    predicted_intent: IntentEnum,
    is_ambiguous: bool,
    settings: Optional[Settings] = None,
) -> Tuple[bool, float, str]:
    """Assess whether retrieved historical support cases provide reliable grounding evidence.

    Returns:
        Tuple of (is_sufficient, top_similarity, reason).
    """
    app_settings = settings or get_settings()

    if not evidence_items:
        return False, 0.0, "No historical support evidence was retrieved."

    top_sim = float(evidence_items[0].similarity)

    # KEY REQUIREMENT: If the request is ambiguous, evidence is NOT sufficient
    # even if surface similarity is high (e.g. 0.80) because the affected feature is unknown.
    if is_ambiguous:
        return (
            False,
            top_sim,
            "Evidence cannot be reliably verified because the customer request is ambiguous.",
        )

    # Check minimum similarity threshold
    min_sim = app_settings.RETRIEVAL_MIN_SIMILARITY
    if top_sim < min_sim:
        return (
            False,
            top_sim,
            f"Top retrieval similarity ({top_sim:.4f}) is below minimum confidence threshold ({min_sim:.2f}).",
        )

    return True, top_sim, f"Relevant historical evidence retrieved with similarity {top_sim:.4f}."


def evaluate_decision_policy(
    conversation: ConversationState,
    predicted_intent: IntentEnum,
    intent_confidence: float,
    evidence_items: List[EvidenceItem],
    settings: Optional[Settings] = None,
) -> Tuple[SupportAction, str, Optional[str], bool, bool, bool, bool, bool]:
    """Execute the multi-signal decision policy.

    Phase 10 Priority Order:
    1. ESCALATE: Sensitive/safety issue or explicit human request
    2. AUTO_HANDLE: Conversation is resolved/closing
    3. ESCALATE: Repeated failed troubleshooting
    4. ESCALATE: Frustration + unresolved issue
    5. CLARIFY: Ambiguous referent
    6. CLARIFY: Low intent confidence (Phase 10: changed from ESCALATE)
    7. CLARIFY: Insufficient retrieval evidence (Phase 10: changed from ESCALATE)
    8. AUTO_HANDLE: Clear, confident, grounded

    Returns:
        Tuple of (action, reason, clarification_question,
                  is_ambiguous, evidence_sufficient, repeated_troubleshooting,
                  is_frustrated, is_resolved_closing).
    """
    app_settings = settings or get_settings()

    # Detect all signals
    is_ambiguous, ambiguity_reason, clarification_q = detect_ambiguity(conversation)
    repeated_troubleshoot, troubleshoot_reason = detect_repeated_troubleshooting(conversation)
    is_sensitive, sensitive_reason = detect_sensitive_escalation(conversation)
    is_resolved_closing, resolved_reason = detect_resolved_closing(conversation)
    is_frustrated, frustration_reason = detect_frustration(conversation)
    evidence_sufficient, top_sim, evidence_reason = assess_evidence(
        evidence_items=evidence_items,
        predicted_intent=predicted_intent,
        is_ambiguous=is_ambiguous,
        settings=app_settings,
    )

    # Helper for return tuple
    def _result(action, reason, clarification=None):
        return (
            action, reason, clarification,
            is_ambiguous, evidence_sufficient, repeated_troubleshoot,
            is_frustrated, is_resolved_closing,
        )

    # --------------------------------------------------------------------------
    # Decision Evaluation Logic (Phase 10 priority order)
    # --------------------------------------------------------------------------

    # Priority 1: ESCALATE — Sensitive/safety issue (unchanged)
    if is_sensitive:
        reason = sensitive_reason or "Issue requires human specialist intervention."
        logger.info("Policy Decision -> ESCALATE (Sensitive Trigger): %s", reason)
        return _result(SupportAction.ESCALATE, reason)

    # Priority 2: AUTO_HANDLE — Resolved/closing conversation (Phase 10 NEW)
    # Only if no repeated troubleshooting and no active frustration with unresolved issue
    if is_resolved_closing and not repeated_troubleshoot:
        reason = resolved_reason or "Customer indicated the issue is resolved."
        logger.info("Policy Decision -> AUTO_HANDLE (Resolved/Closing): %s", reason)
        return _result(SupportAction.AUTO_HANDLE, reason)

    # Priority 3: ESCALATE — Repeated troubleshooting (improved detection)
    if repeated_troubleshoot:
        reason = troubleshoot_reason or (
            "Previous troubleshooting attempts have failed and further assistance "
            "may require a human support specialist."
        )
        logger.info("Policy Decision -> ESCALATE (Repeated Troubleshooting): %s", reason)
        return _result(SupportAction.ESCALATE, reason)

    # Priority 4: ESCALATE — Frustration + unresolved issue (Phase 10 NEW)
    # Frustration alone is NOT sufficient — must co-occur with unresolved issue signals
    if is_frustrated and not is_resolved_closing:
        reason = (
            f"{frustration_reason} The issue appears unresolved. "
            "Escalating to human support specialist."
        )
        logger.info("Policy Decision -> ESCALATE (Frustration + Unresolved): %s", reason)
        return _result(SupportAction.ESCALATE, reason)

    # Priority 5: CLARIFY — Ambiguous referent (unchanged)
    if is_ambiguous:
        reason = ambiguity_reason or "The affected product or feature is unclear."
        logger.info("Policy Decision -> CLARIFY: %s", reason)
        return _result(SupportAction.CLARIFY, reason, clarification_q)

    # Priority 6: CLARIFY — Low intent confidence
    # Phase 10 CHANGE: Previously this was ESCALATE, now CLARIFY
    min_conf = app_settings.INTENT_MIN_CONFIDENCE
    if intent_confidence < min_conf:
        reason = (
            f"Intent classification confidence ({intent_confidence:.2f}) is below safe threshold ({min_conf:.2f}). "
            "Requesting clarification to better understand the issue."
        )
        clarify_q = "Could you please provide more details about the issue you're experiencing?"
        logger.info("Policy Decision -> CLARIFY (Low Intent Confidence): %s", reason)
        return _result(SupportAction.CLARIFY, reason, clarify_q)

    # Priority 7: CLARIFY — Insufficient retrieval evidence
    # Phase 10 CHANGE: Previously this was ESCALATE, now CLARIFY
    if not evidence_sufficient:
        reason = (
            f"Historical evidence is limited ({evidence_reason}). "
            "Requesting additional details to find relevant support guidance."
        )
        clarify_q = "Could you provide a bit more detail about what's happening so we can find the best guidance for you?"
        logger.info("Policy Decision -> CLARIFY (Insufficient Evidence): %s", reason)
        return _result(SupportAction.CLARIFY, reason, clarify_q)

    # Priority 8: AUTO_HANDLE — Clear, confident, grounded (unchanged)
    reason = "The issue is clear and relevant historical evidence is available."
    logger.info(
        "Policy Decision -> AUTO_HANDLE: Intent='%s' (Conf=%.2f, TopSim=%.4f)",
        predicted_intent.value, intent_confidence, top_sim,
    )
    return _result(SupportAction.AUTO_HANDLE, reason)
