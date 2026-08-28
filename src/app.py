"""
app.py — NetSage AI human-review dashboard.

Lets a person pick a case, see the rule-checker / AI diagnosis, and
Approve, Edit, or Reject it. Every decision is logged to
docs/review_log.csv, which becomes your Responsible-AI audit trail.

Run with:
    streamlit run app.py
"""

import json
import csv
import os
from datetime import datetime

import streamlit as st
import pandas as pd

from checker import run_checks
from engine import diagnose_case, load_system_prompt

CASES_PATH = "../data/cases.csv"
LOG_PATH = "../docs/review_log.csv"

st.set_page_config(page_title="NetSage AI — Review Dashboard", layout="wide")


@st.cache_data
def load_cases():
    return pd.read_csv(CASES_PATH)


@st.cache_resource
def get_system_prompt():
    return load_system_prompt()


def log_decision(case_id, decision, ai_root_cause, human_note):
    """Append one review decision to the CSV log (creates folder + file if missing)."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    file_exists = os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "case_id", "decision", "ai_root_cause", "human_note"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"),
                          case_id, decision, ai_root_cause, human_note])


st.title("NetSage AI — Human Review Dashboard")
st.caption("The AI suggests a diagnosis. You approve, edit, or reject it before it counts as final.")

df = load_cases()
system_prompt = get_system_prompt()

case_id = st.selectbox("Pick a case", df["case_id"].tolist())
row = df[df["case_id"] == case_id].iloc[0]

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Case details")
    st.markdown(f"**Symptom:** {row['symptom']}")
    st.markdown(f"**Topology:** {row['topology_note']}")
    st.markdown("**Show-command output:**")
    st.code(row["show_outputs"], language="text")
    st.markdown(f"**Ground-truth fault (for grading only):** {row['expected_fault']}")

with col2:
    st.subheader("AI / Rule diagnosis")

    # Cache the diagnosis per case in session_state so re-rendering
    # (e.g. after clicking a button) doesn't re-call the API each time.
    cache_key = f"diagnosis_{case_id}"
    if cache_key not in st.session_state:
        with st.spinner("Running rule checker and AI diagnosis..."):
            st.session_state[cache_key] = diagnose_case(row, system_prompt)

    result = st.session_state[cache_key]

    source_label = "Rule checker (fast path)" if result.get("source") == "rule" else "AI (Gemini)"
    st.markdown(f"**Source:** {source_label}")
    st.markdown(f"**Root cause:** {result.get('root_cause', 'N/A')}")
    st.markdown(f"**OSI layer:** {result.get('osi_layer', 'N/A')}")
    st.markdown(f"**Confidence:** {result.get('confidence', 'N/A')}")
    st.markdown(f"**Evidence:** {result.get('evidence', 'N/A')}")
    st.markdown(f"**Suggested next command:** `{result.get('next_command', 'N/A')}`")
    st.markdown("**Fix steps:**")
    for step in result.get("fix_steps", []):
        st.markdown(f"- {step}")

st.divider()
st.subheader("Your review")

human_note = st.text_area(
    "Notes (required if editing or rejecting — explain what was wrong)",
    key=f"note_{case_id}",
)

b1, b2, b3 = st.columns(3)

with b1:
    if st.button("✅ Approve", use_container_width=True):
        log_decision(case_id, "Approved", result.get("root_cause", ""), human_note)
        st.success(f"Logged: {case_id} approved.")

with b2:
    if st.button("✏️ Edit / Correct", use_container_width=True):
        if not human_note.strip():
            st.warning("Please add a note explaining the correction before logging an edit.")
        else:
            log_decision(case_id, "Edited", result.get("root_cause", ""), human_note)
            st.success(f"Logged: {case_id} edited with your correction.")

with b3:
    if st.button("❌ Reject", use_container_width=True):
        if not human_note.strip():
            st.warning("Please add a note explaining the rejection before logging it.")
        else:
            log_decision(case_id, "Rejected", result.get("root_cause", ""), human_note)
            st.success(f"Logged: {case_id} rejected.")

st.divider()
st.subheader("Review log so far")
if os.path.exists(LOG_PATH):
    log_df = pd.read_csv(LOG_PATH)
    st.dataframe(log_df, use_container_width=True)

    st.markdown("**Summary by fault type**")
    chart_df = df.merge(log_df, on="case_id", how="inner")
    if not chart_df.empty:
        st.bar_chart(chart_df["concept_tag"].value_counts())
else:
    st.info("No reviews logged yet — approve, edit, or reject a case above to start the log.")