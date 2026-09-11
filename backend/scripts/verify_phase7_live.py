"""Verification script for Phase 7 Grounded LLM Response Generation.

Tests all 4 target scenarios against the decision agent with OpenRouter generation.
"""

import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

scenarios = [
    {
        "name": "Scenario 1: Clear Battery Issue (auto_handle)",
        "payload": {
            "conversation_id": "phase7-battery",
            "messages": [
                {
                    "role": "customer",
                    "text": "My iPhone battery is draining very quickly after the latest update.",
                }
            ],
        },
    },
    {
        "name": "Scenario 2: Ambiguous Single-Turn Query (clarify)",
        "payload": {
            "conversation_id": "phase7-ambiguous",
            "messages": [
                {
                    "role": "customer",
                    "text": "It stopped working after I updated it.",
                }
            ],
        },
    },
    {
        "name": "Scenario 3: Multi-Turn Clarification Follow-up (auto_handle)",
        "payload": {
            "conversation_id": "phase7-multiturn",
            "messages": [
                {
                    "role": "customer",
                    "text": "It stopped working after I updated it.",
                },
                {
                    "role": "assistant",
                    "text": "Could you clarify what stopped working after the update—for example, Wi-Fi, Messages, an app, or another feature?",
                },
                {
                    "role": "customer",
                    "text": "Wi-Fi won't turn on at all now.",
                },
            ],
        },
    },
    {
        "name": "Scenario 4: Repeated Failed Troubleshooting (escalate)",
        "payload": {
            "conversation_id": "phase7-repeated",
            "messages": [
                {
                    "role": "customer",
                    "text": "My iPhone won't connect to Wi-Fi.",
                },
                {
                    "role": "assistant",
                    "text": "Have you tried resetting your network settings?",
                },
                {
                    "role": "customer",
                    "text": "I already tried resetting network settings and restarted my phone, it still won't connect.",
                },
            ],
        },
    },
]

for sc in scenarios:
    print("=" * 80)
    print(f"RUNNING: {sc['name']}")
    print("=" * 80)
    res = client.post("/api/v1/agent", json=sc["payload"])
    print(f"HTTP Status: {res.status_code}")
    data = res.json()
    print(f"Action: {data.get('action')}")
    print(f"Predicted Intent: {data.get('intent')} (Confidence: {data.get('intent_confidence'):.4f})")
    print(f"Top Retrieval Similarity: {data.get('retrieval', {}).get('top_similarity')}")
    print(f"Signals: {data.get('signals')}")
    print(f"Reason: {data.get('reason')}")
    print(f"Generated Response: {data.get('response')}")
    if data.get("clarification_question"):
        print(f"Clarification Question: {data.get('clarification_question')}")
    print()
