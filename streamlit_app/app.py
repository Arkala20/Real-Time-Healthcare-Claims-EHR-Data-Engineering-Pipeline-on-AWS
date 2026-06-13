import os

import pandas as pd
import plotly.express as px
import snowflake.connector
import streamlit as st
from dotenv import load_dotenv

import queries

load_dotenv()

st.set_page_config(
    page_title="Healthcare Pipeline Analytics",
    page_icon="🏥",
    layout="wide",
)

# ── Connection ────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Connecting to Snowflake...")
def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


@st.cache_data(ttl=300, show_spinner="Running query...")
def run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    cur.close()
    return df


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🏥 Healthcare Pipeline")
    st.caption("Real-Time Claims & EHR Analytics")
    st.divider()
    st.info(
        f"**Snowflake**\n\n"
        f"Account: `{os.environ.get('SNOWFLAKE_ACCOUNT', 'not set')}`\n\n"
        f"Database: `{os.environ.get('SNOWFLAKE_DATABASE', 'healthcare')}`\n\n"
        f"Schema: `{os.environ.get('SNOWFLAKE_SCHEMA', 'raw')}`"
    )
    if st.button("Clear cache & refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Title ─────────────────────────────────────────────────────────────────────

st.title("🏥 Healthcare Claims & EHR Dashboard")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_cms, tab_ehr = st.tabs(["Overview", "CMS Claims", "EHR"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

with tab_overview:
    st.subheader("Pipeline KPIs")

    try:
        kpi = run_query(queries.KPI_SUMMARY).iloc[0]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("CMS Patients",       f"{int(kpi['CMS_PATIENTS']):,}")
        col2.metric("Total Claims",        f"{int(kpi['TOTAL_CLAIMS']):,}")
        col3.metric("Total Claims Spend",  f"${int(kpi['TOTAL_CLAIMS_SPEND']):,}")
        col4.metric("Total Prescriptions", f"{int(kpi['TOTAL_PRESCRIPTIONS']):,}")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("EHR Patients",       f"{int(kpi['EHR_PATIENTS']):,}")
        col6.metric("Total Encounters",   f"{int(kpi['TOTAL_ENCOUNTERS']):,}")
        col7.metric("Total Conditions",   f"{int(kpi['TOTAL_CONDITIONS']):,}")
        col8.metric("Total Observations", f"{int(kpi['TOTAL_OBSERVATIONS']):,}")

    except Exception as e:
        st.error(f"Could not load KPIs: {e}")

    st.divider()

    col_left, col_right = st.columns(2)

    # Risk tier pie
    with col_left:
        st.subheader("Patient Risk Tier Distribution")
        try:
            df = run_query(queries.RISK_TIER_DISTRIBUTION)
            fig = px.pie(
                df,
                names="RISK_TIER",
                values="PATIENT_COUNT",
                color_discrete_sequence=px.colors.sequential.RdBu,
                hole=0.35,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # Medication chronic vs acute
    with col_right:
        st.subheader("Medication Type Split")
        try:
            df = run_query(queries.MEDICATION_SPLIT)
            fig = px.pie(
                df,
                names="MEDICATION_TYPE",
                values="PRESCRIPTION_COUNT",
                color_discrete_sequence=["#636EFA", "#EF553B"],
                hole=0.35,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — CMS CLAIMS
# ════════════════════════════════════════════════════════════════════════════

with tab_cms:

    # Claims volume over time
    st.subheader("Claims Volume & Cost by Month")
    try:
        df = run_query(queries.CLAIMS_BY_MONTH)
        col_l, col_r = st.columns(2)
        with col_l:
            fig = px.line(
                df,
                x="MONTH_LABEL",
                y="CLAIM_COUNT",
                color="CLAIM_TYPE",
                markers=True,
                title="Claim Count by Month",
                labels={"MONTH_LABEL": "Month", "CLAIM_COUNT": "Claims", "CLAIM_TYPE": "Type"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with col_r:
            fig = px.bar(
                df,
                x="MONTH_LABEL",
                y="TOTAL_PAYMENT",
                color="CLAIM_TYPE",
                title="Total Payment by Month ($)",
                labels={"MONTH_LABEL": "Month", "TOTAL_PAYMENT": "Total Payment ($)", "CLAIM_TYPE": "Type"},
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")

    st.divider()

    # Top drugs
    st.subheader("Top 10 Prescribed Drugs")
    try:
        df = run_query(queries.TOP_DRUGS)
        fig = px.bar(
            df,
            x="PRESCRIPTION_COUNT",
            y="GENERIC_NAME",
            orientation="h",
            color="TOTAL_COST",
            color_continuous_scale="Blues",
            text="PRESCRIPTION_COUNT",
            title="Prescriptions by Drug (colored by total cost)",
            labels={"PRESCRIPTION_COUNT": "Prescriptions", "GENERIC_NAME": "Drug"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("View raw data"):
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")

    st.divider()

    # High cost patients
    st.subheader("Top 20 High-Cost Patients")
    try:
        df = run_query(queries.HIGH_COST_PATIENTS)
        fig = px.scatter(
            df,
            x="RISK_SCORE",
            y="TOTAL_SPEND",
            color="RISK_TIER",
            size="TOTAL_CLAIMS",
            hover_data=["PATIENT_ID", "AGE_GROUP", "GENDER_LABEL"],
            title="Risk Score vs Total Spend (bubble size = claim count)",
            labels={"RISK_SCORE": "Risk Score", "TOTAL_SPEND": "Total Spend ($)", "RISK_TIER": "Risk Tier"},
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — EHR
# ════════════════════════════════════════════════════════════════════════════

with tab_ehr:

    col_l, col_r = st.columns(2)

    # Top conditions
    with col_l:
        st.subheader("Top 10 Active Conditions")
        try:
            df = run_query(queries.TOP_CONDITIONS)
            fig = px.bar(
                df,
                x="OCCURRENCE_COUNT",
                y="ICD10_DISPLAY",
                orientation="h",
                color="CHRONIC_PCT",
                color_continuous_scale="Reds",
                text="OCCURRENCE_COUNT",
                labels={"OCCURRENCE_COUNT": "Count", "ICD10_DISPLAY": "Condition", "CHRONIC_PCT": "Chronic %"},
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # Encounter breakdown
    with col_r:
        st.subheader("Encounter Type Breakdown")
        try:
            df = run_query(queries.ENCOUNTER_BREAKDOWN)
            fig = px.bar(
                df,
                x="ENCOUNTER_CLASS",
                y=["VISIT_COUNT", "EMERGENCY_VISITS"],
                barmode="group",
                title="Visits by Encounter Class",
                labels={"value": "Count", "ENCOUNTER_CLASS": "Class", "variable": "Type"},
            )
            st.plotly_chart(fig, use_container_width=True)

            fig2 = px.bar(
                df,
                x="ENCOUNTER_CLASS",
                y="AVG_COST",
                color="AVG_DURATION_HOURS",
                color_continuous_scale="Viridis",
                title="Average Cost per Encounter Class",
                labels={"AVG_COST": "Avg Cost ($)", "ENCOUNTER_CLASS": "Class", "AVG_DURATION_HOURS": "Avg Duration (hrs)"},
            )
            st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    col_l2, col_r2 = st.columns(2)

    # Age group vs chronic rate
    with col_l2:
        st.subheader("Age Group vs Chronic Disease Rate")
        try:
            df = run_query(queries.AGE_CHRONIC_RATE)
            fig = px.bar(
                df,
                x="AGE_GROUP",
                y="PCT_WITH_CONDITION",
                color="CHRONIC_CONDITION_COUNT",
                color_continuous_scale="Oranges",
                text="PCT_WITH_CONDITION",
                title="% Patients with Conditions by Age Group",
                labels={"PCT_WITH_CONDITION": "% With Condition", "AGE_GROUP": "Age Group"},
            )
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # Abnormal lab results
    with col_r2:
        st.subheader("Abnormal Lab Results by Category")
        try:
            df = run_query(queries.ABNORMAL_LABS)
            fig = px.bar(
                df,
                x="CATEGORY",
                y=["TOTAL_OBSERVATIONS", "ABNORMAL_COUNT"],
                barmode="overlay",
                title="Total vs Abnormal Observations",
                labels={"value": "Count", "CATEGORY": "Category", "variable": "Type"},
                color_discrete_map={
                    "TOTAL_OBSERVATIONS": "#B0C4DE",
                    "ABNORMAL_COUNT": "#DC143C",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

            fig2 = px.pie(
                df,
                names="CATEGORY",
                values="ABNORMAL_COUNT",
                title="Abnormal Count Share by Category",
                hole=0.35,
            )
            st.plotly_chart(fig2, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")
