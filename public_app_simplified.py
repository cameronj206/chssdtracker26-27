from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st
from supabase import create_client


# ---------------------------------------------------------
# Page setup and visual design
# ---------------------------------------------------------
st.set_page_config(
    page_title="Carrboro High School Swim Practice Tracker",
    page_icon="🏊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PURPLE = "#603A91"
GOLD = "#C6A64B"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

st.markdown(
    f"""
    <style>
        .stApp {{
            background: #08080B;
        }}
        [data-testid="stHeader"] {{
            background: rgba(8, 8, 11, 0.95);
        }}
        [data-testid="stSidebar"] {{
            background: #17121F;
            border-right: 1px solid {PURPLE};
        }}
        h1, h2, h3 {{
            color: #FFFFFF;
        }}
        [data-testid="stMetric"] {{
            background: #17121F;
            border: 1px solid {PURPLE};
            border-radius: 10px;
            padding: 14px;
        }}
        [data-testid="stMetricLabel"] {{
            color: #C5B1E8;
        }}
        [data-testid="stMetricValue"] {{
            color: {GOLD};
        }}
        div[data-baseweb="tab-list"] button[aria-selected="true"] {{
            border-bottom-color: {GOLD};
            color: {GOLD};
        }}
        .site-subtitle {{
            color: #C5B1E8;
            margin-top: -12px;
        }}
        .gold-rule {{
            border: 0;
            border-top: 2px solid {GOLD};
            margin: 8px 0 22px 0;
        }}
        .practice-card {{
            background: #17121F;
            border: 1px solid #603A91;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 14px;
        }}
        .practice-card h3 {{
            margin-top: 0;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# Read-only Supabase connection
# ---------------------------------------------------------
@st.cache_resource
def get_public_client():
    """Connect using the Supabase anon/publishable key, never the service-role key."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_ANON_KEY"]
    except Exception as exc:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_ANON_KEY in Streamlit secrets."
        ) from exc

    return create_client(url, key)


@st.cache_data(ttl=60)
def load_public_data():
    """
    Load only information intended for the public practice tracker.
    Private general_notes and group_notes are deliberately not selected.
    """
    client = get_public_client()

    groups_response = (
        client.table("training_groups")
        .select("id, group_name")
        .eq("is_active", True)
        .order("group_name")
        .execute()
    )

    weeks_response = (
        client.table("weeks")
        .select("week_number, start_date, end_date")
        .order("week_number")
        .execute()
    )

    workouts_response = (
        client.table("workouts")
        .select(
            """
            id,
            week_number,
            practice_date,
            day_of_week,
            session_name,
            workout_description,
            is_no_practice,
            group_workout_entries (
                id,
                total_yardage,
                duration_minutes,
                practice_type,
                training_groups (
                    id,
                    group_name
                )
            )
            """
        )
        .order("practice_date")
        .order("created_at")
        .execute()
    )

    return (
        groups_response.data or [],
        weeks_response.data or [],
        workouts_response.data or [],
    )


def as_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def format_yards(value):
    return f"{as_int(value):,}"


def format_week_dates(week):
    start = week.get("start_date")
    end = week.get("end_date")
    if start and end:
        start_date = date.fromisoformat(start) if isinstance(start, str) else start
        end_date = date.fromisoformat(end) if isinstance(end, str) else end
        return f"{start_date.strftime('%b %-d')} – {end_date.strftime('%b %-d, %Y')}"
    return "Dates not set"


def get_group_entries(workout):
    return workout.get("group_workout_entries") or []


def get_entry_group_name(entry):
    group = entry.get("training_groups") or {}
    return group.get("group_name", "Training group")


def get_day_total(workouts, day):
    total = 0
    for workout in workouts:
        if workout.get("day_of_week") == day:
            total += sum(as_int(e.get("total_yardage")) for e in get_group_entries(workout))
    return total


def build_week_overview_rows(workouts):
    """One row per day, showing distinct group practice types and total daily yards."""
    rows = []
    for day in DAYS:
        day_workouts = [w for w in workouts if w.get("day_of_week") == day]
        if not day_workouts:
            practice_type = "Not entered"
        elif all(w.get("is_no_practice") for w in day_workouts):
            practice_type = "No Practice"
        else:
            types = set()
            for workout in day_workouts:
                if workout.get("is_no_practice"):
                    continue
                for entry in get_group_entries(workout):
                    types.add(entry.get("practice_type") or "Not specified")
            practice_type = ", ".join(sorted(types)) if types else "Not specified"
        rows.append({
            "Day": day,
            "Practice Type": practice_type,
            "Total Yards": get_day_total(workouts, day),
        })
    rows.append({
        "Day": "Weekly total",
        "Practice Type": "",
        "Total Yards": sum(get_day_total(workouts, day) for day in DAYS),
    })
    return pd.DataFrame(rows)


def get_week_group_totals(workouts):
    totals = {}
    for workout in workouts:
        for entry in get_group_entries(workout):
            group_name = get_entry_group_name(entry)
            totals[group_name] = totals.get(group_name, 0) + as_int(
                entry.get("total_yardage")
            )
    return totals


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------
logo_path = Path(__file__).with_name("logo_outline.webp")
header_logo, header_title = st.columns([1, 8], vertical_alignment="center")
with header_logo:
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
with header_title:
    st.title("Carrboro High School Swim Practice Tracker")
st.markdown(
    '<p class="site-subtitle">2026–2027 Season · Weekly Training Log</p>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------
try:
    groups, weeks, all_workouts = load_public_data()
except Exception as exc:
    st.error("The public tracker could not connect to its database.")
    st.info(
        "Check that the public app has SUPABASE_URL and SUPABASE_ANON_KEY "
        "configured, and that the read-only Supabase policies have been applied."
    )
    st.exception(exc)
    st.stop()

if not weeks:
    st.warning("No season weeks are currently available.")
    st.stop()

week_numbers = [int(w["week_number"]) for w in weeks]
week_lookup = {int(w["week_number"]): w for w in weeks}


# ---------------------------------------------------------
# Season overview
# ---------------------------------------------------------
st.subheader("Season overview")

season_yards = sum(
    as_int(entry.get("total_yardage"))
    for workout in all_workouts
    for entry in get_group_entries(workout)
)
season_sessions = sum(not w.get("is_no_practice", False) for w in all_workouts)

metric1, metric2 = st.columns(2)
metric1.metric("Season yardage", f"{season_yards:,}")
metric2.metric("Practice sessions", f"{season_sessions:,}")

weekly_totals = []
for week in weeks:
    week_number = int(week["week_number"])
    week_workouts = [
        w for w in all_workouts if int(w.get("week_number", -1)) == week_number
    ]
    total = sum(
        as_int(entry.get("total_yardage"))
        for workout in week_workouts
        for entry in get_group_entries(workout)
    )
    weekly_totals.append(
        {"Week": f"Week {week_number}", "Total Yards": total}
    )

st.markdown("### Weekly yardage progression")
st.caption("Combined yardage across all training groups for each week.")

weekly_chart_df = pd.DataFrame(weekly_totals)
if not weekly_chart_df.empty:
    st.bar_chart(
        weekly_chart_df,
        x="Week",
        y="Total Yards",
        color=GOLD,
        y_label="Total yards",
        x_label="Season week",
    )
else:
    st.info("Weekly yardage will appear as practices are added.")


# Current calendar week's daily overview, directly below the season chart.
today = date.today()
current_week = next(
    (
        week for week in weeks
        if date.fromisoformat(week["start_date"]) <= today
        <= date.fromisoformat(week["end_date"])
    ),
    None,
)
if current_week is not None:
    current_number = int(current_week["week_number"])
    current_workouts = [
        workout for workout in all_workouts
        if int(workout.get("week_number", -1)) == current_number
    ]
    st.markdown("### Current weekly overview")
    st.caption(f"Week {current_number} · {format_week_dates(current_week)}")
    st.dataframe(
        build_week_overview_rows(current_workouts),
        use_container_width=True,
        hide_index=True,
        column_config={"Total Yards": st.column_config.NumberColumn("Total Yards", format="%d")},
    )
else:
    st.caption("The current date falls outside the tracked swim season.")


# ---------------------------------------------------------
# Weekly practice tracker
# ---------------------------------------------------------
st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)
st.subheader("Weekly practice tracker")

selected_week_number = st.selectbox(
    "Select a season week",
    week_numbers,
    format_func=lambda n: f"Week {n} · {format_week_dates(week_lookup[n])}",
)

selected_week = week_lookup[selected_week_number]
week_workouts = [
    w for w in all_workouts
    if int(w.get("week_number", -1)) == int(selected_week_number)
]

st.markdown(f"### Week {selected_week_number}")
st.caption(format_week_dates(selected_week))

# ---------------------------------------------------------
# Daily practice details
# ---------------------------------------------------------
st.markdown("#### Daily practices")
day_tabs = st.tabs(DAYS)

for tab, day in zip(day_tabs, DAYS):
    with tab:
        day_workouts = [
            w for w in week_workouts if w.get("day_of_week") == day
        ]

        if not day_workouts:
            st.info(f"No {day} practices have been published yet.")
            continue

        if all(w.get("is_no_practice") for w in day_workouts):
            st.info("No Practice")
            continue
        st.metric(f"{day} total yardage", f"{get_day_total(week_workouts, day):,}")

        for workout in day_workouts:
            if workout.get("is_no_practice"):
                st.info("No Practice")
                continue
            session_name = workout.get("session_name") or "Practice"
            practice_date = workout.get("practice_date") or ""
            description = workout.get("workout_description") or ""

            with st.container(border=True):
                st.subheader(session_name)
                if practice_date:
                    st.caption(practice_date)

                if description.strip():
                    st.markdown(description)
                else:
                    st.caption("No shared workout description has been added.")

                entries = get_group_entries(workout)
                if entries:
                    st.markdown("**Training-group breakdown**")
                    entry_rows = []
                    for entry in entries:
                        entry_rows.append(
                            {
                                "Training Group": get_entry_group_name(entry),
                                "Practice Type": entry.get("practice_type") or "Not specified",
                                "Total Yards": as_int(entry.get("total_yardage")),
                                "Duration (minutes)": as_int(
                                    entry.get("duration_minutes")
                                ),
                            }
                        )

                    entries_df = pd.DataFrame(entry_rows)
                    st.dataframe(
                        entries_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Total Yards": st.column_config.NumberColumn(
                                "Total Yards", format="%d"
                            ),
                            "Duration (minutes)": st.column_config.NumberColumn(
                                "Duration (minutes)", format="%d"
                            ),
                        },
                    )
                else:
                    st.caption("No training-group yardage has been entered.")

st.markdown('<hr class="gold-rule">', unsafe_allow_html=True)
st.caption(
    "Carrboro High School Swim Practice Tracker · Public, read-only practice information"
)
