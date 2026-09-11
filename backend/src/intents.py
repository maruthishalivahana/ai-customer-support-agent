"""Intent taxonomy, domain keyword signatures, and rule-based labeling helpers.

Defines rich domain patterns for the 12 AppleSupport intents to support
supervised training on historical interactions without touching the Golden Set.
"""

import re
from typing import Dict, List, Pattern
from src.schemas import Intent, IntentEnum


# ==============================================================================
# Domain Keyword Signatures & Patterns for the 12 Canonical Intents
# ==============================================================================

INTENT_PATTERNS: Dict[Intent, List[str]] = {
    IntentEnum.BATTERY_CHARGING: [
        r"\bbatter(?:y|ies)\b",
        r"\bdrain(?:ing|ed|s)?\b",
        r"\bcharg(?:er|ing|ed|es)?\b",
        r"\bpower(?:ing)?\s*down\b",
        r"\bshuts?\s*down\b",
        r"\bdead\s*battery\b",
        r"\bbattery\s*health\b",
        r"\bpercentage\b",
        r"\boverheat(?:ing|ed)?\b",
    ],
    IntentEnum.CONNECTIVITY: [
        r"\bwi-?fi\b",
        r"\bbluetooth\b",
        r"\bcellular\b",
        r"\blte\b",
        r"\b4g\b",
        r"\b3g\b",
        r"\bnetwork\b",
        r"\bcarrier\b",
        r"\bsignal\b",
        r"\bhotspot\b",
        r"\bdisconnect(?:ing|ed|s)?\b",
        r"\bno\s*service\b",
        r"\bairpods?\b",
    ],
    IntentEnum.APPLE_ID_ACCOUNT: [
        r"\bapple\s*id\b",
        r"\bpasscode\b",
        r"\bpassword\b",
        r"\blogin\b",
        r"\blog\s*in\b",
        r"\bsign\s*in\b",
        r"\blocked\s*out\b",
        r"\biforgot\b",
        r"\btwo-?factor\b",
        r"\b2fa\b",
        r"\bverification\s*code\b",
        r"\bsecurity\s*question\b",
    ],
    IntentEnum.ICLOUD_BACKUP_DATA: [
        r"\bicloud\b",
        r"\bback-?up(?:s|ed|ing)?\b",
        r"\brestore(?:d|ing)?\b",
        r"\bsync(?:ing|ed)?\b",
        r"\bicloud\s*storage\b",
        r"\bicloud\s*drive\b",
        r"\btransfer(?:ring)?\s*data\b",
    ],
    IntentEnum.APP_STORE_PURCHASES: [
        r"\bapp\s*store\b",
        r"\bitunes\s*store\b",
        r"\bpurchas(?:e|ed|ing|es)\b",
        r"\bsubscription(?:s)?\b",
        r"\brefund(?:s|ed|ing)?\b",
        r"\bbill(?:ing)?\b",
        r"\breceipt\b",
        r"\bapple\s*pay\b",
        r"\bcredit\s*card\b",
        r"\bpayment\s*method\b",
        r"\bcharged\s*me\b",
        r"\bunauthorized\s*charge\b",
    ],
    IntentEnum.MESSAGES_CALLING: [
        r"\bimessage\b",
        r"\bmessages?\b",
        r"\btext(?:ing|s|ed)?\b",
        r"\bsms\b",
        r"\bcall(?:ing|s|ed)?\b",
        r"\bphone\s*call\b",
        r"\bvoicemail\b",
        r"\bfacetime\b",
        r"\bcontacts?\b",
        r"\bgreen\s*bubble\b",
        r"\bblue\s*bubble\b",
    ],
    IntentEnum.MUSIC_MEDIA: [
        r"\bapple\s*music\b",
        r"\bitunes\b",
        r"\bmusic\b",
        r"\bsong(?:s)?\b",
        r"\bplaylist(?:s)?\b",
        r"\bradio\b",
        r"\bbeats\b",
        r"\balbum(?:s)?\b",
        r"\baudio\b",
        r"\bvideo(?:s)?\b",
        r"\bphotos?\b",
        r"\bpictures?\b",
        r"\bpodcast(?:s)?\b",
    ],
    IntentEnum.SETTINGS_FEATURES: [
        r"\bsettings?\b",
        r"\bnotifications?\b",
        r"\balarm(?:s)?\b",
        r"\bflashlight\b",
        r"\bsiri\b",
        r"\bcontrol\s*center\b",
        r"\bkeyboard\b",
        r"\bautocorrect\b",
        r"\bwidget(?:s)?\b",
        r"\bwallpaper\b",
        r"\bbrightness\b",
        r"\bdo\s*not\s*disturb\b",
        r"\bdnd\b",
        r"\bdark\s*mode\b",
    ],
    IntentEnum.DEVICE_HARDWARE: [
        r"\bscreen\b",
        r"\bdisplay\b",
        r"\bglass\b",
        r"\bcracked\b",
        r"\btouch\s*screen\b",
        r"\bunresponsive\b",
        r"\bblack\s*screen\b",
        r"\bbutton(?:s)?\b",
        r"\bhome\s*button\b",
        r"\bvolume\s*button\b",
        r"\bpower\s*button\b",
        r"\bcamera\b",
        r"\bspeaker(?:s)?\b",
        r"\bmicrophone\b",
        r"\bheadphone\s*jack\b",
        r"\blightning\s*port\b",
    ],
    IntentEnum.APP_ISSUE: [
        r"\bapps?\s*crashes?\b",
        r"\bapps?\s*freez(?:es|ing)?\b",
        r"\bapps?\s*clos(?:es|ing)?\b",
        r"\bdownload(?:ing)?\s*apps?\b",
        r"\bupdate\s*apps?\b",
        r"\bwhatsapp\b",
        r"\byoutube\b",
        r"\btwitter\b",
        r"\bfacebook\b",
        r"\binstagram\b",
        r"\bsnapchat\b",
        r"\bnetflix\b",
        r"\bspotify\b",
        r"\bsafari\b",
        r"\bmail\s*app\b",
    ],
    IntentEnum.IOS_SOFTWARE: [
        r"\bios\b",
        r"\bios\s*1[1-7]\b",
        r"\bupdate(?:d|ing|s)?\b",
        r"\bsoftware\s*update\b",
        r"\bfirmware\b",
        r"\bupgrade(?:d|ing)?\b",
        r"\binstall(?:ed|ing)?\b",
        r"\bboot\s*loop\b",
        r"\bapple\s*logo\b",
        r"\bfreez(?:es|ing|ed)?\b",
        r"\bglitch(?:es|y)?\b",
        r"\brestart(?:ing|ed|s)?\b",
        r"\breboot\b",
        r"\bbeta\b",
    ],
}

# Precompile regex patterns for performance
COMPILED_PATTERNS: Dict[Intent, List[Pattern]] = {
    intent: [re.compile(p, re.IGNORECASE) for p in patterns]
    for intent, patterns in INTENT_PATTERNS.items()
}


def rule_based_intent_labeler(text: str) -> Intent:
    """Classify text using high-precision domain keyword and regex signatures.

    IMPORTANT NOTE ON DATA QUALITY:
    This function generates heuristic/silver training labels across the historical support
    cases to enable supervised classifier training. These labels are distinct from the human-reviewed
    ground truth evaluation labels present exclusively in `data/apple_goldset.csv`.

    Args:
        text: Customer message text.

    Returns:
        Intent category. Defaults to Intent.OTHER_GENERAL if no domain patterns match.
    """
    if not text or not text.strip():
        return Intent.OTHER_GENERAL

    lower_text = text.lower()

    # Match counts per intent
    scores: Dict[Intent, int] = {}
    for intent, patterns in COMPILED_PATTERNS.items():
        score = sum(1 for p in patterns if p.search(lower_text))
        if score > 0:
            scores[intent] = score

    if not scores:
        return IntentEnum.OTHER_GENERAL

    # Priority order for ties (more specific intents first)
    priority_order = [
        IntentEnum.BATTERY_CHARGING,
        IntentEnum.APPLE_ID_ACCOUNT,
        IntentEnum.APP_STORE_PURCHASES,
        IntentEnum.ICLOUD_BACKUP_DATA,
        IntentEnum.MESSAGES_CALLING,
        IntentEnum.CONNECTIVITY,
        IntentEnum.DEVICE_HARDWARE,
        IntentEnum.MUSIC_MEDIA,
        IntentEnum.SETTINGS_FEATURES,
        IntentEnum.APP_ISSUE,
        IntentEnum.IOS_SOFTWARE,
        IntentEnum.OTHER_GENERAL,
    ]

    max_score = max(scores.values())
    candidates = [intent for intent, score in scores.items() if score == max_score]

    for p_intent in priority_order:
        if p_intent in candidates:
            return p_intent

    return candidates[0]
