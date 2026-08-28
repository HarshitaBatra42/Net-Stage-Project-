"""
engine.py — Combines checker.py (rules) and the AI model into one pipeline.

Logic for each case:
  1. Run the rule checker on show_outputs.
  2. If the rule checker found something -> use that as the answer (fast, free, reliable).
  3. If the rule checker found nothing -> ask the AI (Gemini) to reason about it,
     using the prompt template in prompts/diagnose_prompt.md.
  4. Always return the same shape of result, so app.py can display either
     source the same way, and always tag which source ("rule" or "ai") produced it.

Usage:
    python engine.py            # runs all 32 cases, prints a summary
    python engine.py NET-003    # runs just one case, prints full detail
"""

import os
import sys
import json
import re
import requests
import pandas as pd
from dotenv import load_dotenv

from checker import run_checks

load_dotenv()  # reads GEMINI_API_KEY from your .env file

API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-3-flash-preview"

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "diagnose_prompt.md")
CASES_PATH = "../data/cases.csv"


def load_system_prompt() -> str:
    """Read diagnose_prompt.md so it can be sent as context to the AI."""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def ask_ai(symptom: str, topology_note: str, show_outputs: str, system_prompt: str) -> dict:
    """Send one case to Gemini and parse its JSON reply."""
    if not API_KEY:
        return {
            "root_cause": "AI not called — no GEMINI_API_KEY found in .env",
            "osi_layer": "N/A",
            "confidence": "Low",
            "evidence": "Missing API key",
            "next_command": "N/A",
            "fix_steps": ["Add GEMINI_API_KEY to your .env file"],
        }

    user_message = (
        f"SYMPTOM: {symptom}\n"
        f"TOPOLOGY_NOTE: {topology_note}\n"
        f"SHOW_OUTPUT:\n{show_outputs}"
    )

    body = {
        "model": GEMINI_MODEL,
        "input": system_prompt + "\n\n" + user_message,
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": API_KEY,
        "Api-Revision": "2026-05-20",
    }

    try:
        response = requests.post(GEMINI_URL, json=body, headers=headers, timeout=30)
        if response.status_code != 200:
            # Show Google's real error message, not just "404 Not Found"
            return {
                "root_cause": f"AI call failed: HTTP {response.status_code} — {response.text[:400]}",
                "osi_layer": "N/A",
                "confidence": "Low",
                "evidence": "N/A",
                "next_command": "N/A",
                "fix_steps": ["See the exact error message above and fix accordingly"],
            }

        data = response.json()
        # Interactions API returns a "steps" list; the reply text is inside
        # the step with type "model_output".
        raw_text = ""
        for step in data.get("steps", []):
            if step.get("type") == "model_output":
                for block in step.get("content", []):
                    if block.get("type") == "text":
                        raw_text += block["text"]

        # Strip markdown code fences if the model added them despite instructions
        cleaned = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip())
        return json.loads(cleaned)

    except Exception as e:
        return {
            "root_cause": f"AI call failed: {e}",
            "osi_layer": "N/A",
            "confidence": "Low",
            "evidence": "N/A",
            "next_command": "N/A",
            "fix_steps": ["Check your API key and internet connection, then retry"],
        }


def diagnose_case(row: pd.Series, system_prompt: str) -> dict:
    """Run the full pipeline (rules -> AI fallback) for one case row."""
    check_result = run_checks(row["show_outputs"])

    if check_result["status"] == "ERRORS_DETECTED":
        top_flag = check_result["flags"][0]
        return {
            "case_id": row["case_id"],
            "source": "rule",
            "root_cause": top_flag["message"],
            "osi_layer": row.get("osi_layer", "N/A"),
            "confidence": "High",
            "evidence": f"Matched rule: {top_flag['rule']}",
            "next_command": "N/A (caught by rule checker)",
            "fix_steps": ["Reviewed by rule checker — human should confirm and apply fix."],
        }

    ai_result = ask_ai(row["symptom"], row["topology_note"], row["show_outputs"], system_prompt)
    ai_result["case_id"] = row["case_id"]
    ai_result["source"] = "ai"
    return ai_result


def run_all():
    df = pd.read_csv(CASES_PATH)
    system_prompt = load_system_prompt()
    results = [diagnose_case(row, system_prompt) for _, row in df.iterrows()]
    return results


if __name__ == "__main__":
    df = pd.read_csv(CASES_PATH)
    system_prompt = load_system_prompt()

    if len(sys.argv) > 1:
        case_id = sys.argv[1]
        row = df[df["case_id"] == case_id].iloc[0]
        result = diagnose_case(row, system_prompt)
        print(json.dumps(result, indent=2))
    else:
        results = run_all()
        rule_count = sum(1 for r in results if r["source"] == "rule")
        ai_count = sum(1 for r in results if r["source"] == "ai")
        print(f"Diagnosed {len(results)} cases: {rule_count} by rules, {ai_count} by AI")
        for r in results[:3]:
            print(json.dumps(r, indent=2))
