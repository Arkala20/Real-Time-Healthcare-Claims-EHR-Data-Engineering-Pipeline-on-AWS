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


def chart(fig):
    st.plotly_chart(fig, use_container_width=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🏥 Healthcare Pipeline")
    st.caption("Real-Time Claims & EHR Analytics")
    st.divider()
    st.info(
        f"**Snowflake**\n\n"
        f"Account: `{os.environ.get('SNOWFLAKE_ACCOUNT', 'not set')}`\n\n"
        f"DB / Schema: `{os.environ.get('SNOWFLAKE_DATABASE', 'healthcare')}`"
        f" / `{os.environ.get('SNOWFLAKE_SCHEMA', 'raw')}`"
    )
    if st.button("Clear cache & refresh"):
        st.cache_data.clear()
        st.rerun()

st.title("🏥 Healthcare Claims & EHR Dashboard")

tab_overview, tab_cms, tab_ehr, tab_diag = st.tabs(
    ["Overview", "CMS Claims", "EHR", "Diagnostics"]
)

# ════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

with tab_overview:
    try:
        k = run_query(queries.KPI_SUMMARY).iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("CMS Patients",       f"{int(k['CMS_PATIENTS']):,}")
        c2.metric("Total Claims",        f"{int(k['TOTAL_CLAIMS']):,}")
        c3.metric("Claims Spend",        f"${int(k['TOTAL_CLAIMS_SPEND']):,}")
        c4, c5, c6 = st.columns(3)
        c4.metric("EHR Patients",        f"{int(k['EHR_PATIENTS']):,}")
        c5.metric("Encounters",          f"{int(k['TOTAL_ENCOUNTERS']):,}")
        c6.metric("Prescriptions",       f"{int(k['TOTAL_PRESCRIPTIONS']):,}")
        c7, c8, _ = st.columns(3)
        c7.metric("Medications (EHR)",   f"{int(k['TOTAL_MEDICATIONS']):,}")
        c8.metric("Observations (EHR)",  f"{int(k['TOTAL_OBSERVATIONS']):,}")
    except Exception as e:
        st.error(f"KPI error: {e}")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Patient Risk Distribution")
        try:
            df = run_query(queries.RISK_SCORE_DISTRIBUTION)
            fig = px.pie(
                df, names="RISK_TIER", values="PATIENT_COUNT",
                color_discrete_sequence=["#2ecc71", "#f39c12", "#e74c3c"],
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    with col_r:
        st.subheader("Patient Age Group")
        try:
            df = run_query(queries.PATIENT_AGE_GROUP)
            fig = px.bar(
                df, x="AGE_GROUP", y="PATIENT_COUNT",
                color="AVG_RISK_SCORE", color_continuous_scale="Reds",
                text="PATIENT_COUNT",
                labels={"PATIENT_COUNT": "Patients", "AGE_GROUP": "Age Group", "AVG_RISK_SCORE": "Avg Risk"},
            )
            fig.update_traces(textposition="outside")
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    st.subheader("Gender × Race Breakdown")
    try:
        df = run_query(queries.PATIENT_GENDER_RACE)
        fig = px.bar(
            df, x="RACE_LABEL", y="PATIENT_COUNT",
            color="GENDER_LABEL", barmode="group",
            labels={"PATIENT_COUNT": "Patients", "RACE_LABEL": "Race", "GENDER_LABEL": "Gender"},
        )
        chart(fig)
    except Exception as e:
        st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# CMS CLAIMS
# ════════════════════════════════════════════════════════════════════════════

with tab_cms:

    # Claims over time
    st.subheader("Claims Volume & Spend by Month")
    try:
        df = run_query(queries.CLAIMS_BY_MONTH)
        col_l, col_r = st.columns(2)
        with col_l:
            fig = px.bar(
                df, x="MONTH_LABEL", y="CLAIM_COUNT",
                text="CLAIM_COUNT",
                labels={"MONTH_LABEL": "Month", "CLAIM_COUNT": "Claims"},
                title="Claim Count per Month",
            )
            fig.update_traces(textposition="outside")
            chart(fig)
        with col_r:
            fig = px.line(
                df, x="MONTH_LABEL", y="TOTAL_PAYMENT",
                markers=True,
                labels={"MONTH_LABEL": "Month", "TOTAL_PAYMENT": "Total Payment ($)"},
                title="Total Payment per Month",
            )
            chart(fig)
    except Exception as e:
        st.error(f"Error: {e}")

    st.divider()

    # Payment buckets
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Payment Amount Buckets")
        try:
            df = run_query(queries.PAYMENT_BUCKETS)
            fig = px.bar(
                df, x="PAYMENT_BUCKET", y="CLAIM_COUNT",
                color="TOTAL_PAYMENT", color_continuous_scale="Blues",
                text="CLAIM_COUNT",
                labels={"PAYMENT_BUCKET": "Bucket", "CLAIM_COUNT": "Claims"},
            )
            fig.update_traces(textposition="outside")
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    with col_r:
        st.subheader("Top 10 Prescribed Drugs")
        try:
            df = run_query(queries.TOP_DRUGS)
            fig = px.bar(
                df, x="PRESCRIPTION_COUNT", y="GENERIC_NAME",
                orientation="h",
                color="TOTAL_COST", color_continuous_scale="Purples",
                text="PRESCRIPTION_COUNT",
                labels={"PRESCRIPTION_COUNT": "Prescriptions", "GENERIC_NAME": "Drug"},
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    # High cost patients scatter
    st.subheader("Top 20 High-Cost Patients")
    try:
        df = run_query(queries.HIGH_COST_PATIENTS)
        fig = px.scatter(
            df, x="RISK_SCORE", y="TOTAL_SPEND",
            color="RISK_TIER", size="TOTAL_CLAIMS",
            hover_data=["PATIENT_ID", "AGE_GROUP", "GENDER_LABEL"],
            color_discrete_map={"Low": "#2ecc71", "Medium": "#f39c12", "High": "#e74c3c"},
            labels={"RISK_SCORE": "Risk Score", "TOTAL_SPEND": "Total Spend ($)", "RISK_TIER": "Risk Tier"},
            title="Risk Score vs Total Spend  (bubble size = claim count)",
        )
        chart(fig)
        with st.expander("View table"):
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# EHR
# ════════════════════════════════════════════════════════════════════════════

with tab_ehr:

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Encounter Class Breakdown")
        try:
            df = run_query(queries.ENCOUNTER_BY_CLASS)
            fig = px.pie(
                df, names="ENCOUNTER_CLASS", values="VISIT_COUNT",
                hole=0.4,
                title="Visits by Class",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            chart(fig)

            fig2 = px.bar(
                df, x="ENCOUNTER_CLASS", y="AVG_COST",
                color="AVG_COST", color_continuous_scale="Oranges",
                text="AVG_COST",
                labels={"ENCOUNTER_CLASS": "Class", "AVG_COST": "Avg Cost ($)"},
                title="Avg Cost per Encounter Class",
            )
            fig2.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
            chart(fig2)
        except Exception as e:
            st.error(f"Error: {e}")

    with col_r:
        st.subheader("Encounters by Month")
        try:
            df = run_query(queries.ENCOUNTERS_BY_MONTH)
            fig = px.bar(
                df, x="MONTH_LABEL", y="ENCOUNTER_COUNT",
                text="ENCOUNTER_COUNT",
                labels={"MONTH_LABEL": "Month", "ENCOUNTER_COUNT": "Encounters"},
                title="Encounter Count per Month",
            )
            fig.update_traces(textposition="outside")
            chart(fig)

            fig2 = px.line(
                df, x="MONTH_LABEL", y="TOTAL_COST",
                markers=True,
                labels={"MONTH_LABEL": "Month", "TOTAL_COST": "Total Cost ($)"},
                title="Encounter Total Cost per Month",
            )
            chart(fig2)
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    col_l2, col_r2 = st.columns(2)

    with col_l2:
        st.subheader("Top 10 Medications")
        try:
            df = run_query(queries.TOP_MEDICATIONS)
            fig = px.bar(
                df, x="PRESCRIPTION_COUNT", y="DRUG_NAME",
                orientation="h",
                color="CHRONIC_COUNT", color_continuous_scale="Reds",
                text="PRESCRIPTION_COUNT",
                labels={"PRESCRIPTION_COUNT": "Count", "DRUG_NAME": "Drug", "CHRONIC_COUNT": "Chronic Rxs"},
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    with col_r2:
        st.subheader("Medication: Chronic vs Acute")
        try:
            df = run_query(queries.MEDICATION_CHRONIC_SPLIT)
            fig = px.pie(
                df, names="MED_TYPE", values="COUNT",
                color_discrete_sequence=["#e74c3c", "#3498db"],
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            chart(fig)
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    st.subheader("Top Lab Tests & Abnormal Rates")
    try:
        col_l3, col_r3 = st.columns(2)
        with col_l3:
            df = run_query(queries.TOP_OBSERVATIONS)
            fig = px.bar(
                df, x="OBS_COUNT", y="OBSERVATION_NAME",
                orientation="h",
                color="ABNORMAL_PCT", color_continuous_scale="RdYlGn_r",
                text="OBS_COUNT",
                labels={"OBS_COUNT": "Count", "OBSERVATION_NAME": "Test", "ABNORMAL_PCT": "Abnormal %"},
                title="Observation Volume (color = abnormal %)",
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            chart(fig)

        with col_r3:
            df2 = run_query(queries.ABNORMAL_BY_TEST)
            fig = px.bar(
                df2, x="ABNORMAL_PCT", y="TEST_NAME",
                orientation="h",
                color="ABNORMAL_PCT", color_continuous_scale="Reds",
                text="ABNORMAL_PCT",
                labels={"ABNORMAL_PCT": "Abnormal %", "TEST_NAME": "Test"},
                title="Abnormal Rate by Lab Test (%)",
            )
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            chart(fig)
    except Exception as e:
        st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# DIAGNOSTICS
# ════════════════════════════════════════════════════════════════════════════

with tab_diag:
    st.subheader("Table Row Counts")
    try:
        df = run_query(queries.TABLE_ROW_COUNTS)
        fig = px.bar(
            df, x="TABLE_NAME", y="ROW_COUNT",
            color="ROW_COUNT", color_continuous_scale="Blues",
            text="ROW_COUNT", title="Rows per Table",
        )
        fig.update_layout(xaxis_tickangle=-30)
        fig.update_traces(textposition="outside")
        chart(fig)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")

    st.divider()
    st.subheader("Sample Data Viewer")
    tbl = st.selectbox("Table:", ["dim_patient_cms", "fact_claims", "fact_encounters", "fact_medications"])
    sample_map = {
        "dim_patient_cms": queries.SAMPLE_CMS_PATIENT,
        "fact_claims":     queries.SAMPLE_FACT_CLAIMS,
        "fact_encounters": queries.SAMPLE_ENCOUNTERS,
        "fact_medications": queries.SAMPLE_MEDICATIONS,
    }
    try:
        df = run_query(sample_map[tbl])
        st.dataframe(df, use_container_width=True)
        null_pct = (df.isnull().sum() / len(df) * 100).reset_index()
        null_pct.columns = ["Column", "Null %"]
        null_pct = null_pct[null_pct["Null %"] > 0].sort_values("Null %", ascending=False)
        if not null_pct.empty:
            st.markdown("**Columns with nulls in this sample:**")
            st.dataframe(null_pct, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")
