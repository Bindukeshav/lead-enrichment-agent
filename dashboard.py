"""Quick visual viewer for the agent's output.

Run with: streamlit run dashboard.py
"""
import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Lead Enrichment Results", layout="wide")
st.title("🔍 Lead Enrichment Agent — Results")

output_path = st.text_input("Output JSON path", value="output/output.json")

if not Path(output_path).exists():
    st.warning(f"No file found at `{output_path}` yet — run main.py first.")
    st.stop()

with open(output_path) as f:
    data = json.load(f)

if not data:
    st.info("The output file is empty — every domain may have failed. Check terminal logs.")
    st.stop()

for entry in data:
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(entry["domain"])
            st.write(entry["company_overview"])
            st.caption(f"**Target audience:** {entry['target_audience']}")
        with col2:
            score = entry["data_confidence_score"]
            st.metric("Confidence", f"{score:.0%}")

        if entry["contact_points"]:
            st.write("**Contacts:** " + ", ".join(entry["contact_points"]))
        else:
            st.write("**Contacts:** _none found_")

        if entry["key_team_members"]:
            st.write("**Team:**")
            for member in entry["key_team_members"]:
                link = f" — [{member['linkedin_url']}]({member['linkedin_url']})" if member.get("linkedin_url") else ""
                st.write(f"- {member['name']} ({member.get('role') or 'role unknown'}){link}")
        else:
            st.write("**Team:** _none found_")
