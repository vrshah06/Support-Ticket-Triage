import os
import sys
import time
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MODEL,
    OPENAI_API_KEY,
)
from classifier import TicketClassifier, OPENAI_AVAILABLE
from processor import TicketProcessor

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="AI Support Ticket Triage",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border: 1px solid #e9ecef;
        text-align: center;
    }
    .badge-urgent {
        background-color: #ffebee;
        color: #c62828;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-high {
        background-color: #fff3e0;
        color: #e65100;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-medium {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 4px 8px;
        border-radius: 4px;
    }
    .badge-low {
        background-color: #e3f2fd;
        color: #1565c0;
        padding: 4px 8px;
        border-radius: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "processor" not in st.session_state:
    st.session_state.processor = TicketProcessor()
if "is_processed" not in st.session_state:
    st.session_state.is_processed = False
if "api_key" not in st.session_state:
    st.session_state.api_key = OPENAI_API_KEY
if "model" not in st.session_state:
    st.session_state.model = DEFAULT_MODEL
if "confidence_threshold" not in st.session_state:
    st.session_state.confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD

# Sidebar Navigation and Configuration
st.sidebar.title("🎫 Ticket Triage AI")
st.sidebar.caption("Intelligent Support Ticket Classification & Human Review")

nav_choice = st.sidebar.radio(
    "Navigation",
    [
        "📊 Dashboard",
        "📂 Upload Tickets",
        "⚡ Process Tickets",
        "📋 All Tickets",
        "👤 Human Review Queue",
        "💾 Reports & Downloads",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ System Configuration")

user_api_key = st.sidebar.text_input(
    "OpenAI API Key",
    value=st.session_state.api_key,
    type="password",
    help="Leave blank to use mock/heuristic classifier for offline demo",
)
if user_api_key != st.session_state.api_key or (user_api_key and getattr(st.session_state.processor.classifier, "_client", None) is None):
    st.session_state.api_key = user_api_key
    st.session_state.processor.classifier.set_api_key(user_api_key)

selected_model = st.sidebar.selectbox(
    "Model",
    ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
    index=0,
)
st.session_state.model = selected_model
st.session_state.processor.classifier.model = selected_model

conf_threshold = st.sidebar.slider(
    "Confidence Threshold",
    min_value=0.50,
    max_value=0.95,
    value=st.session_state.confidence_threshold,
    step=0.05,
    help="Tickets with confidence below this threshold route to Human Review",
)
st.session_state.confidence_threshold = conf_threshold

if not OPENAI_AVAILABLE:
    st.sidebar.warning(
        "⚠️ 'openai' package is not installed in the currently running Python environment.\n"
        "Running in Heuristic / Offline mode.\n"
        "To enable OpenAI API, run:\n`pip install openai`"
    )
    mode_text = "🟡 Heuristic / Offline (openai uninstalled)"
elif st.session_state.api_key:
    mode_text = "🟢 OpenAI API"
else:
    mode_text = "🟡 Heuristic / Offline (No API key set)"

st.sidebar.info(
    f"Active Mode: {mode_text}\n\n"
    f"Threshold: {conf_threshold:.2f}"
)

# Automatically load sample candidate dataset if not yet loaded
candidate_csv = os.path.join(os.path.dirname(__file__), "candidate", "tickets.csv")
if not st.session_state.processor.tickets and os.path.exists(candidate_csv):
    with open(candidate_csv, "r", encoding="utf-8") as f:
        st.session_state.processor.load_and_validate_csv(f)

# If outputs/results.csv exists on disk and session not processed, pre-load results
results_csv = os.path.join(os.path.dirname(__file__), "outputs", "results.csv")
if not st.session_state.is_processed and os.path.exists(results_csv) and st.session_state.processor.tickets:
    st.session_state.processor.process_all_tickets(confidence_threshold=st.session_state.confidence_threshold)
    st.session_state.is_processed = True


# ==============================================================================
# SECTION 1: DASHBOARD
# ==============================================================================
if nav_choice == "📊 Dashboard":
    st.title("📊 Support Ticket Triage Dashboard")
    st.markdown("Real-time monitoring of AI classification throughput, confidence routing, and review status.")

    stats = st.session_state.processor.get_summary_stats()
    total = stats.get("total_tickets", 0)

    # Key Performance Metric Cards
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric("Total Tickets", total)
    with c2:
        st.metric("Successfully Classified", stats.get("successfully_classified", 0))
    with c3:
        st.metric("Auto-Approved", stats.get("automatically_classified", 0))
    with c4:
        st.metric("Needs Human Review", stats.get("human_review_count", 0))
    with c5:
        st.metric("Human Reviewed", stats.get("human_reviewed_count", 0))
    with c6:
        st.metric("Urgent Escalations", stats.get("urgent_tickets", 0))

    if total == 0:
        st.warning("No tickets have been loaded. Please visit '📂 Upload Tickets' to begin.")
    elif not st.session_state.is_processed:
        st.info("Tickets loaded but not yet processed. Please navigate to '⚡ Process Tickets' to run triage.")
    else:
        st.markdown("---")
        ch1, ch2 = st.columns(2)

        with ch1:
            st.subheader("Priority Distribution")
            p_dist = stats.get("priority_distribution", {})
            fig_pri = px.pie(
                values=list(p_dist.values()),
                names=list(p_dist.keys()),
                color=list(p_dist.keys()),
                color_discrete_map={
                    "Urgent": "#d32f2f",
                    "High": "#f57c00",
                    "Medium": "#388e3c",
                    "Low": "#1976d2",
                },
                hole=0.45,
            )
            fig_pri.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_pri, width="stretch")

        with ch2:
            st.subheader("Category Distribution")
            c_dist = stats.get("category_distribution", {})
            df_cat = pd.DataFrame(list(c_dist.items()), columns=["Category", "Count"])
            fig_cat = px.bar(
                df_cat,
                x="Category",
                y="Count",
                color="Category",
                color_discrete_sequence=px.colors.qualitative.Plotly,
            )
            fig_cat.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_cat, width="stretch")

        st.subheader("Triage Routing Status")
        status_counts = {
            "Auto-Classified (Confidence >= 0.80)": stats.get("automatically_classified", 0),
            "Human Review (Low Confidence / Urgent)": stats.get("human_review_count", 0) - stats.get("human_reviewed_count", 0),
            "Human Confirmed": stats.get("human_reviewed_count", 0),
            "Failed": stats.get("failed_tickets", 0),
        }
        df_status = pd.DataFrame(list(status_counts.items()), columns=["Status", "Tickets"])
        fig_status = px.bar(
            df_status,
            x="Tickets",
            y="Status",
            orientation="h",
            color="Status",
            color_discrete_map={
                "Auto-Classified (Confidence >= 0.80)": "#2e7d32",
                "Human Review (Low Confidence / Urgent)": "#f57c00",
                "Human Confirmed": "#0288d1",
                "Failed": "#d32f2f",
            },
        )
        st.plotly_chart(fig_status, width="stretch")


# ==============================================================================
# SECTION 2: UPLOAD TICKETS
# ==============================================================================
elif nav_choice == "📂 Upload Tickets":
    st.title("📂 Upload Tickets Dataset")
    st.markdown("Upload customer support tickets in CSV format or load the built-in 300-ticket assessment dataset.")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

        if uploaded_file is not None:
            valid, errors = st.session_state.processor.load_and_validate_csv(uploaded_file)
            if valid:
                st.success(f"Successfully loaded and validated {len(st.session_state.processor.tickets)} tickets!")
                st.session_state.is_processed = False
            else:
                st.error("CSV Validation Failed:")
                for err in errors:
                    st.write(f"- {err}")

    with col2:
        st.markdown("#### Quick Load")
        if st.button("🔄 Reset to 300 Candidate Dataset", width="stretch"):
            if os.path.exists(candidate_csv):
                with open(candidate_csv, "r", encoding="utf-8") as f:
                    valid, errors = st.session_state.processor.load_and_validate_csv(f)
                if valid:
                    st.success("Candidate dataset (300 tickets) loaded successfully!")
                    st.session_state.is_processed = False
            else:
                st.error("candidate/tickets.csv not found.")

    if st.session_state.processor.tickets:
        st.markdown("---")
        st.subheader("Dataset Preview")
        preview_df = pd.DataFrame(st.session_state.processor.tickets).head(10)
        st.dataframe(preview_df, width="stretch")


# ==============================================================================
# SECTION 3: PROCESS TICKETS
# ==============================================================================
elif nav_choice == "⚡ Process Tickets":
    st.title("⚡ AI Ticket Triage Execution")
    st.markdown("Execute batch AI classification and confidence-based routing for loaded tickets.")

    total_tickets = len(st.session_state.processor.tickets)
    st.write(f"**Loaded Tickets:** `{total_tickets}`")
    st.write(f"**Target Model:** `{st.session_state.model}`")
    st.write(f"**Confidence Threshold:** `{st.session_state.confidence_threshold:.2f}`")

    if total_tickets == 0:
        st.warning("Please upload or load tickets in '📂 Upload Tickets' before processing.")
    else:
        if st.button("🚀 Run Triage Pipeline", type="primary", width="stretch"):
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def progress_cb(current, total, msg):
                progress_bar.progress(current / total)
                status_text.text(msg)

            with st.spinner("Processing tickets..."):
                stats = st.session_state.processor.process_all_tickets(
                    confidence_threshold=st.session_state.confidence_threshold,
                    progress_callback=progress_cb,
                )
                st.session_state.is_processed = True

                # Export mandatory results immediately
                out_dir = os.path.join(os.path.dirname(__file__), "outputs")
                os.makedirs(out_dir, exist_ok=True)
                st.session_state.processor.export_results_csv(os.path.join(out_dir, "results.csv"))
                st.session_state.processor.export_report_json(os.path.join(out_dir, "report.json"))

            st.success("Triage execution completed successfully!")
            progress_bar.progress(1.0)
            status_text.text(f"Processed {total_tickets} tickets in {stats['processing_duration_seconds']}s.")

            # Summary badges
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Successfully Classified", stats["successfully_classified"])
            m2.metric("Automatically Approved", stats["automatically_classified"])
            m3.metric("Sent to Human Review", stats["human_review_count"])
            m4.metric("Urgent Escalations", stats["urgent_tickets"])


# ==============================================================================
# SECTION 4: ALL TICKETS
# ==============================================================================
elif nav_choice == "📋 All Tickets":
    st.title("📋 All Tickets")
    st.markdown("Browse, filter, and inspect detailed triage records.")

    if not st.session_state.is_processed:
        st.info("Tickets have not been processed yet. Navigate to '⚡ Process Tickets' to run triage.")
    else:
        results_list = list(st.session_state.processor.results.values())
        df_all = pd.DataFrame(results_list)

        # Filters
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            status_filter = st.selectbox("Status", ["All"] + list(df_all["status"].unique()))
        with f2:
            cat_filter = st.selectbox("Category", ["All"] + ALLOWED_CATEGORIES)
        with f3:
            pri_filter = st.selectbox("Priority", ["All"] + ALLOWED_PRIORITIES)
        with f4:
            search_query = st.text_input("Search (ID, Subject, Body)", "")

        filtered = df_all.copy()
        if status_filter != "All":
            filtered = filtered[filtered["status"] == status_filter]
        if cat_filter != "All":
            filtered = filtered[
                (filtered["final_category"] == cat_filter) | (filtered["ai_category"] == cat_filter)
            ]
        if pri_filter != "All":
            filtered = filtered[
                (filtered["final_priority"] == pri_filter) | (filtered["ai_priority"] == pri_filter)
            ]
        if search_query:
            q = search_query.lower()
            filtered = filtered[
                filtered["id"].str.lower().str.contains(q)
                | filtered["subject"].str.lower().str.contains(q)
                | filtered["body"].str.lower().str.contains(q)
            ]

        st.caption(f"Showing {len(filtered)} of {len(df_all)} tickets")

        display_cols = [
            "id",
            "subject",
            "ai_category",
            "ai_priority",
            "ai_confidence",
            "needs_review",
            "status",
            "final_category",
            "final_priority",
        ]
        st.dataframe(filtered[display_cols], width="stretch")

        # Detailed ticket inspector
        st.markdown("---")
        st.subheader("🔍 Ticket Inspector")
        inspect_id = st.selectbox("Select Ticket ID to Inspect", filtered["id"].tolist())
        if inspect_id:
            ticket_detail = st.session_state.processor.results.get(inspect_id, {})
            d1, d2 = st.columns([1, 1])
            with d1:
                st.markdown(f"**Ticket ID:** `{ticket_detail.get('id')}`")
                st.markdown(f"**Customer:** {ticket_detail.get('customer')}")
                st.markdown(f"**Subject:** {ticket_detail.get('subject')}")
                st.markdown(f"**Customer Message:**")
                st.text_area("Body", ticket_detail.get("body", ""), height=180, disabled=True)
            with d2:
                st.markdown(f"**AI Category:** `{ticket_detail.get('ai_category')}`")
                st.markdown(f"**AI Priority:** `{ticket_detail.get('ai_priority')}`")
                st.markdown(f"**Confidence:** `{ticket_detail.get('ai_confidence')}`")
                st.markdown(f"**Routing Status:** `{ticket_detail.get('status')}`")
                st.markdown(f"**Routing Reason:** {ticket_detail.get('review_reason')}")
                st.markdown(f"**AI Explanation:** {ticket_detail.get('ai_explanation')}")


# ==============================================================================
# SECTION 5: HUMAN REVIEW QUEUE
# ==============================================================================
elif nav_choice == "👤 Human Review Queue":
    st.title("👤 Human Review Queue")
    st.markdown(
        "Review uncertain tickets (confidence < 0.80), conservative escalations (urgent/high-risk), or empty bodies. "
        "Original AI predictions are preserved separately from human corrections."
    )

    if not st.session_state.is_processed:
        st.info("Tickets have not been processed yet. Navigate to '⚡ Process Tickets' to run triage.")
    else:
        review_tickets = [
            r for r in st.session_state.processor.results.values()
            if r.get("needs_review") == "yes" and not r.get("is_human_reviewed", False)
        ]
        reviewed_tickets = [
            r for r in st.session_state.processor.results.values()
            if r.get("is_human_reviewed", False)
        ]

        t1, t2 = st.tabs([f"Pending Review ({len(review_tickets)})", f"Completed Reviews ({len(reviewed_tickets)})"])

        with t1:
            if not review_tickets:
                st.success("🎉 Human review queue is empty! All review tickets have been processed.")
            else:
                for idx, t in enumerate(review_tickets[:15]):  # Show first 15 for responsiveness
                    tid = t["id"]
                    with st.expander(f"📌 {tid} - {t.get('subject', '(No Subject)')} [Reason: {t.get('review_reason')}]", expanded=(idx==0)):
                        r_col1, r_col2 = st.columns([3, 2])

                        with r_col1:
                            st.markdown(f"**Customer:** {t.get('customer')}")
                            st.markdown(f"**Subject:** {t.get('subject')}")
                            st.text_area(f"Message ({tid})", t.get("body", ""), height=140, disabled=True, key=f"body_{tid}")
                            st.caption(f"Reason: {t.get('review_reason')}")

                        with r_col2:
                            st.markdown("#### AI Proposal")
                            st.write(f"- Proposed Category: `{t.get('ai_category') or 'None'}`")
                            st.write(f"- Proposed Priority: `{t.get('ai_priority') or 'None'}`")
                            st.write(f"- Confidence: `{t.get('ai_confidence')}`")
                            st.caption(f"Explanation: {t.get('ai_explanation')}")

                            st.markdown("#### Human Review Decision")
                            # Default selector to AI prediction if available, else first option
                            def_cat_idx = ALLOWED_CATEGORIES.index(t["ai_category"]) if t.get("ai_category") in ALLOWED_CATEGORIES else 0
                            def_pri_idx = ALLOWED_PRIORITIES.index(t["ai_priority"]) if t.get("ai_priority") in ALLOWED_PRIORITIES else 1

                            h_cat = st.selectbox("Category", ALLOWED_CATEGORIES, index=def_cat_idx, key=f"h_cat_{tid}")
                            h_pri = st.selectbox("Priority", ALLOWED_PRIORITIES, index=def_pri_idx, key=f"h_pri_{tid}")

                            if st.button(f"✅ Confirm Classification ({tid})", key=f"btn_confirm_{tid}", type="primary"):
                                st.session_state.processor.apply_human_review(tid, h_cat, h_pri)
                                # Update results.csv and report.json immediately
                                out_dir = os.path.join(os.path.dirname(__file__), "outputs")
                                st.session_state.processor.export_results_csv(os.path.join(out_dir, "results.csv"))
                                st.session_state.processor.export_report_json(os.path.join(out_dir, "report.json"))
                                st.success(f"Ticket {tid} classified as {h_cat} / {h_pri}!")
                                st.rerun()

        with t2:
            if not reviewed_tickets:
                st.info("No tickets have been human-reviewed yet.")
            else:
                df_rev = pd.DataFrame(reviewed_tickets)[
                    ["id", "subject", "ai_category", "ai_priority", "human_category", "human_priority", "status"]
                ]
                st.dataframe(df_rev, width="stretch")


# ==============================================================================
# SECTION 6: REPORTS & DOWNLOADS
# ==============================================================================
elif nav_choice == "💾 Reports & Downloads":
    st.title("💾 Reports & Mandatory Deliverables")
    st.markdown("Export official assessment deliverables (`results.csv` and `report.json`).")

    out_dir = os.path.join(os.path.dirname(__file__), "outputs")
    res_path = os.path.join(out_dir, "results.csv")
    rep_path = os.path.join(out_dir, "report.json")

    # Refresh exports if processed
    if st.session_state.is_processed:
        st.session_state.processor.export_results_csv(res_path)
        st.session_state.processor.export_report_json(rep_path)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📄 results.csv")
        st.markdown(
            "Contains exactly the four required columns: `id, category, priority, needs_review`.\n"
            "Exactly one row per input ticket."
        )
        if os.path.exists(res_path):
            with open(res_path, "r", encoding="utf-8") as f:
                csv_bytes = f.read().encode("utf-8")
            st.download_button(
                label="📥 Download results.csv",
                data=csv_bytes,
                file_name="results.csv",
                mime="text/csv",
                type="primary",
                width="stretch",
            )
            df_preview = pd.read_csv(res_path)
            st.dataframe(df_preview.head(15), width="stretch")
        else:
            st.warning("results.csv has not been generated yet. Please run triage first.")

    with col2:
        st.subheader("📊 report.json")
        st.markdown(
            "Contains total tickets, classified counts, routing metrics, distributions, and accuracy disclaimers."
        )
        if os.path.exists(rep_path):
            with open(rep_path, "r", encoding="utf-8") as f:
                json_str = f.read()
            st.download_button(
                label="📥 Download report.json",
                data=json_str.encode("utf-8"),
                file_name="report.json",
                mime="application/json",
                width="stretch",
            )
            st.json(json.loads(json_str))
        else:
            st.warning("report.json has not been generated yet. Please run triage first.")
