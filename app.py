import io
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

from database import (
    get_client,
    get_groups,
    get_weeks,
    get_week_workouts,
    get_all_workouts,
    create_group,
    create_workout,
    update_workout,
    delete_workout,
    save_group_entry,
    delete_group_entry,
    update_week,
)

st.set_page_config(
    page_title="CHSSD Swim Season Tracker",
    page_icon="🏊",
    layout="wide",
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PRACTICE_TYPES = ["Not specified", "Kick", "Stroke/IM", "Sprint", "Distance", "Recovery", "General", "Free"]
YARDAGE_FIELDS = [
    ("warmup_yardage", "Warm-up"),
    ("kick_yardage", "Kick"),
    ("pull_yardage", "Pull"),
    ("main_set_yardage", "Main set"),
    ("cooldown_yardage", "Cooldown"),
    ("other_yardage", "Other"),
]


def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def require_password():
    """Simple shared-password gate for a private, coach-only deployment."""
    app_password = get_secret("APP_PASSWORD", "")
    if not app_password:
        st.error(
            "The app password has not been configured. Add APP_PASSWORD to "
            "your Streamlit secrets before using this app."
        )
        st.code('APP_PASSWORD = "choose-a-long-unique-password"')
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.title("🏊 CHSSD Swim Season Tracker")
    st.write("Enter the team dashboard password to continue.")
    with st.form("login_form"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        if entered == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("That password was not correct.")
    st.stop()


def as_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def next_weekday(target_weekday):
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


def week_date_default(week_row, day_index):
    start = week_row.get("start_date")
    if start:
        if isinstance(start, str):
            start = date.fromisoformat(start)
        return start + timedelta(days=day_index)
    return next_weekday(day_index)


def flatten_workouts(workouts):
    rows = []
    for workout in workouts:
        entries = workout.get("group_workout_entries") or []
        for entry in entries:
            group = entry.get("training_groups") or {}
            rows.append({
                "date": workout.get("practice_date"),
                "week_number": workout.get("week_number"),
                "day": workout.get("day_of_week"),
                "session": workout.get("session_name"),
                "group": group.get("group_name", "Unknown group"),
                "total_yardage": as_int(entry.get("total_yardage")),
                "duration_minutes": as_int(entry.get("duration_minutes")),
                "warmup_yardage": as_int(entry.get("warmup_yardage")),
                "kick_yardage": as_int(entry.get("kick_yardage")),
                "pull_yardage": as_int(entry.get("pull_yardage")),
                "main_set_yardage": as_int(entry.get("main_set_yardage")),
                "cooldown_yardage": as_int(entry.get("cooldown_yardage")),
                "other_yardage": as_int(entry.get("other_yardage")),
                "workout_description": workout.get("workout_description") or "",
                "general_notes": workout.get("general_notes") or "",
                "group_notes": entry.get("group_notes") or "",
                "workout_id": workout.get("id"),
                "group_entry_id": entry.get("id"),
            })
    return rows


def format_number(number):
    return f"{int(number):,}"


def render_group_entry(workout, entry, all_groups):
    group_info = entry.get("training_groups") or {}
    group_name = group_info.get("group_name", "Training group")
    with st.expander(
        f"{group_name} — {format_number(entry.get('total_yardage', 0))} yards",
        expanded=False,
    ):
        st.caption("Yardage and duration are recorded separately for each group.")
        with st.form(f"entry_{entry['id']}"):
            total = st.number_input(
                "Total yardage",
                min_value=0,
                step=100,
                value=as_int(entry.get("total_yardage")),
                key=f"total_{entry['id']}",
            )
            duration = st.number_input(
                "Duration (minutes)",
                min_value=0,
                step=5,
                value=as_int(entry.get("duration_minutes")),
                key=f"duration_{entry['id']}",
            )
            cols = st.columns(3)
            field_values = {}
            for idx, (field, label) in enumerate(YARDAGE_FIELDS):
                with cols[idx % 3]:
                    field_values[field] = st.number_input(
                        f"{label} yardage",
                        min_value=0,
                        step=100,
                        value=as_int(entry.get(field)),
                        key=f"{field}_{entry['id']}",
                    )
            practice_type = st.selectbox(
                "Practice type",
                PRACTICE_TYPES,
                index=PRACTICE_TYPES.index(entry.get("practice_type") or "Not specified")
                if (entry.get("practice_type") or "Not specified") in PRACTICE_TYPES else 0,
                key=f"practice_type_{entry['id']}",
            )
            group_notes = st.text_area(
                "Group-specific notes",
                value=entry.get("group_notes") or "",
                key=f"group_notes_{entry['id']}",
            )
            saved = st.form_submit_button("Save group entry", type="primary")
            if saved:
                values = {
                    "total_yardage": int(total),
                    "duration_minutes": int(duration),
                    **{k: int(v) for k, v in field_values.items()},
                    "group_notes": group_notes,
                    "practice_type": None if practice_type == "Not specified" else practice_type,
                }
                save_group_entry(
                    workout_id=workout["id"],
                    group_id=group_info["id"],
                    values=values,
                    entry_id=entry["id"],
                )
                st.success("Group practice saved.")
                st.rerun()

        if st.button("Remove this group from the workout", key=f"remove_{entry['id']}"):
            delete_group_entry(entry["id"])
            st.success("Group entry removed.")
            st.rerun()


def render_workout(workout, groups):
    session = workout.get("session_name") or "Practice"
    when = workout.get("practice_date", "")
    with st.container(border=True):
        st.subheader(f"{session} · {when}")
        if workout.get("is_no_practice"):
            st.info("No Practice")
            with st.expander("Change No Practice status"):
                if st.button("Restore as a practice", key=f"restore_{workout['id']}"):
                    update_workout(workout["id"], {"is_no_practice": False})
                    st.rerun()
            if st.button("Delete No Practice entry", key=f"delete_no_practice_{workout['id']}"):
                delete_workout(workout["id"])
                st.rerun()
            return
        entries = workout.get("group_workout_entries") or []
        if entries:
            for entry in entries:
                render_group_entry(workout, entry, groups)
        else:
            st.info("No training groups have been assigned to this workout yet.")

        assigned_ids = {
            (entry.get("training_groups") or {}).get("id")
            for entry in entries
        }
        available = [
            g for g in groups
            if g["id"] not in assigned_ids
        ]
        if available:
            with st.expander("Add another training group to this workout"):
                with st.form(f"add_group_{workout['id']}"):
                    group_options = {g["group_name"]: g["id"] for g in available}
                    chosen_name = st.selectbox("Training group", list(group_options))
                    new_total = st.number_input("Total yardage", min_value=0, step=100)
                    new_duration = st.number_input("Duration (minutes)", min_value=0, step=5)
                    new_type = st.selectbox("Practice type", PRACTICE_TYPES)
                    add = st.form_submit_button("Add group")
                    if add:
                        save_group_entry(
                            workout_id=workout["id"],
                            group_id=group_options[chosen_name],
                            values={
                                "total_yardage": int(new_total),
                                "duration_minutes": int(new_duration),
                                "practice_type": None if new_type == "Not specified" else new_type,
                            },
                        )
                        st.success("Training group added.")
                        st.rerun()

        with st.expander("Edit shared workout details"):
            with st.form(f"edit_workout_{workout['id']}"):
                session_name = st.text_input(
                    "Session name",
                    value=workout.get("session_name") or "Practice",
                )
                description = st.text_area(
                    "Workout description",
                    value=workout.get("workout_description") or "",
                    height=150,
                )
                notes = st.text_area(
                    "General notes",
                    value=workout.get("general_notes") or "",
                )
                no_practice_edit = st.checkbox("No Practice", value=bool(workout.get("is_no_practice")))
                save = st.form_submit_button("Save workout details")
                if save:
                    update_workout(
                        workout["id"],
                        {
                            "session_name": session_name.strip() or "Practice",
                            "workout_description": description,
                            "general_notes": notes,
                            "is_no_practice": no_practice_edit,
                        },
                    )
                    st.success("Workout updated.")
                    st.rerun()

        with st.expander("Delete this practice session"):
            st.warning("Deleting a session also deletes its group-specific entries.")
            if st.button("Delete practice session", key=f"delete_{workout['id']}"):
                delete_workout(workout["id"])
                st.success("Practice deleted.")
                st.rerun()


def render_day(day, day_index, week_row, groups, workouts):
    st.subheader(f"{day} practices")
    day_workouts = [w for w in workouts if w.get("day_of_week") == day]
    if day_workouts:
        for workout in day_workouts:
            render_workout(workout, groups)
    else:
        st.info("No practices have been entered for this day.")

    if not groups:
        st.warning("Create at least one training group in the sidebar before adding a practice.")
        return

    with st.expander(f"+ Add a {day} practice", expanded=not day_workouts):
        group_names = [g["group_name"] for g in groups]
        selected_names = st.multiselect(
            "Groups completing this workout",
            group_names,
            default=group_names,
            key=f"new_groups_{week_row['week_number']}_{day}",
        )
        group_lookup = {g["group_name"]: g["id"] for g in groups}
        yardages = {}
        durations = {}
        practice_types = {}

        with st.form(f"new_workout_{week_row['week_number']}_{day}"):
            practice_date = st.date_input(
                "Practice date",
                value=week_date_default(week_row, day_index),
                key=f"date_{week_row['week_number']}_{day}",
            )
            st.caption(f"The selected date must be a {day}.")
            session_name = st.text_input(
                "Session name",
                value="Practice",
                help="For example: Morning practice, Afternoon practice, or Dryland.",
            )
            description = st.text_area(
                "Shared workout description",
                height=130,
                help="Enter the workout once here. It can be assigned to multiple groups.",
            )
            general_notes = st.text_area("General notes")
            no_practice = st.checkbox("No Practice (entire day)", key=f"no_practice_{week_row['week_number']}_{day}")
            if selected_names:
                st.markdown("**Group-specific totals**")
                for name in selected_names:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        yardages[name] = st.number_input(
                            f"{name} total yardage",
                            min_value=0,
                            step=100,
                            key=f"new_yards_{week_row['week_number']}_{day}_{name}",
                        )
                    with c2:
                        durations[name] = st.number_input(
                            f"{name} duration (minutes)",
                            min_value=0,
                            step=5,
                            key=f"new_duration_{week_row['week_number']}_{day}_{name}",
                        )
                    with c3:
                        practice_types[name] = st.selectbox(
                            f"{name} practice type", PRACTICE_TYPES,
                            key=f"new_type_{week_row['week_number']}_{day}_{name}",
                        )
            submitted = st.form_submit_button("Create practice / mark No Practice", type="primary")
            if submitted:
                if practice_date.weekday() != day_index:
                    st.error(f"Please select a date that falls on {day}.")
                elif not selected_names and not no_practice:
                    st.error("Select at least one training group.")
                else:
                    group_values = [
                        {
                            "group_id": group_lookup[name],
                            "total_yardage": int(yardages[name]),
                            "duration_minutes": 0 if no_practice else int(durations[name]),
                            "practice_type": None if no_practice or practice_types[name] == "Not specified" else practice_types[name],
                        }
                        for name in ([] if no_practice else selected_names)
                    ]
                    create_workout(
                        week_number=week_row["week_number"],
                        practice_date=practice_date,
                        day=day,
                        session_name=session_name.strip() or "Practice",
                        description=description,
                        general_notes=general_notes,
                        group_values=group_values,
                        is_no_practice=no_practice,
                    )
                    st.success("Practice created.")
                    st.rerun()


def render_recap(week_row, workouts, groups):
    week_number = week_row["week_number"]
    st.subheader(f"Week {week_number} recap")

    rows = flatten_workouts(workouts)
    week_rows = rows
    total_yards = sum(r["total_yardage"] for r in week_rows)
    group_practices = len(week_rows)
    unique_sessions = len({r["workout_id"] for r in week_rows})
    average = round(total_yards / group_practices) if group_practices else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Combined group yardage", format_number(total_yards))
    c2.metric("Practice sessions", unique_sessions)
    c3.metric("Group practice entries", group_practices)
    c4.metric("Average per group entry", format_number(average))

    st.markdown("### Training group breakdown")
    if week_rows:
        group_df = pd.DataFrame(week_rows)
        summary = (
            group_df.groupby("group", as_index=False)
            .agg(
                practices=("workout_id", "nunique"),
                total_yardage=("total_yardage", "sum"),
                average_yardage=("total_yardage", "mean"),
                total_minutes=("duration_minutes", "sum"),
            )
        )
        summary["average_yardage"] = summary["average_yardage"].round().astype(int)
        summary = summary.rename(columns={
            "group": "Training group",
            "practices": "Sessions",
            "total_yardage": "Total yardage",
            "average_yardage": "Average yardage",
            "total_minutes": "Total minutes",
        })
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.bar_chart(summary.set_index("Training group")["Total yardage"])
    else:
        st.info("Weekly statistics will appear after practices are entered.")

    st.markdown("### Weekly notes")
    with st.form(f"recap_notes_{week_number}"):
        notes = st.text_area(
            "Record observations, progress, meet preparation, or adjustments.",
            value=week_row.get("recap_notes") or "",
            height=160,
        )
        saved = st.form_submit_button("Save weekly recap", type="primary")
        if saved:
            update_week(week_number, {"recap_notes": notes})
            st.success("Weekly recap saved.")
            st.rerun()

    with st.expander("Set this week's date range"):
        current_start = week_row.get("start_date")
        current_end = week_row.get("end_date")
        if isinstance(current_start, str):
            current_start = date.fromisoformat(current_start)
        if isinstance(current_end, str):
            current_end = date.fromisoformat(current_end)
        with st.form(f"week_dates_{week_number}"):
            start = st.date_input(
                "Week starts (Monday)",
                value=current_start or next_weekday(0),
                key=f"week_start_{week_number}",
            )
            end = st.date_input(
                "Week ends (Friday)",
                value=current_end or (start + timedelta(days=4)),
                key=f"week_end_{week_number}",
            )
            saved_dates = st.form_submit_button("Save week dates")
            if saved_dates:
                if start.weekday() != 0 or end.weekday() != 4 or end < start:
                    st.error("Choose a Monday start date and a Friday end date.")
                else:
                    update_week(
                        week_number,
                        {"start_date": start.isoformat(), "end_date": end.isoformat()},
                    )
                    st.success("Week dates saved.")
                    st.rerun()


def main():
    st.title("🏊 CHSSD Swim Season Tracker")
    st.caption("2026–2027 · Team training log")

    require_password()

    try:
        client = get_client()
        groups = get_groups(client)
        weeks = get_weeks(client)
    except Exception as exc:
        st.error("Could not connect to Supabase. Check your Streamlit secrets.")
        st.exception(exc)
        st.stop()

    with st.sidebar:
        st.header("Season navigation")
        st.caption("2026–2027")
        with st.expander("Manage training groups", expanded=not groups):
            with st.form("create_group_form", clear_on_submit=True):
                new_group = st.text_input("New group name", placeholder="e.g. Varsity")
                add_group = st.form_submit_button("Add training group")
                if add_group:
                    if new_group.strip():
                        try:
                            create_group(client, new_group.strip())
                            st.success("Group created.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not create group: {exc}")
                    else:
                        st.warning("Enter a group name.")

            if groups:
                st.write("Current groups:")
                for group in groups:
                    st.write(f"• {group['group_name']}")

        if st.button("Log out"):
            st.session_state["authenticated"] = False
            st.rerun()

    all_workouts = get_all_workouts(client)
    all_rows = flatten_workouts(all_workouts)
    total_yardage = sum(r["total_yardage"] for r in all_rows)
    total_entries = len(all_rows)
    total_sessions = len({r["workout_id"] for r in all_rows})

    st.subheader("Season overview")
    m1, m2, m3 = st.columns(3)
    m1.metric("Season yardage (all groups)", format_number(total_yardage))
    m2.metric("Practice sessions", total_sessions)
    m3.metric("Group practice entries", total_entries)

    if all_rows:
        season_df = pd.DataFrame(all_rows)
        weekly = (
            season_df.groupby("week_number", as_index=False)["total_yardage"]
            .sum()
            .sort_values("week_number")
        )
        st.markdown("### Weekly yardage progression")
        st.line_chart(weekly.set_index("week_number")["total_yardage"])
    else:
        st.info("Add training groups in the sidebar, then start entering practices.")

    st.divider()
    st.subheader("Weekly training log")
    week_numbers = [w["week_number"] for w in weeks]
    if not week_numbers:
        st.error("No weeks were found in the database. Check the weeks table.")
        st.stop()

    selected_week_number = st.selectbox(
        "Select a week",
        week_numbers,
        format_func=lambda n: f"Week {n}",
    )
    week_row = next(w for w in weeks if w["week_number"] == selected_week_number)
    workouts = get_week_workouts(client, selected_week_number)

    tabs = st.tabs(DAYS + ["Weekly Recap"])
    for index, day in enumerate(DAYS):
        with tabs[index]:
            render_day(day, index, week_row, groups, workouts)
    with tabs[-1]:
        render_recap(week_row, workouts, groups)

    st.divider()
    st.subheader("Export season data")
    if all_rows:
        export_df = pd.DataFrame(all_rows).sort_values(
            ["week_number", "date", "day", "session", "group"]
        )
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name="chssd_swim_season_2026_27.csv",
            mime="text/csv",
        )

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, sheet_name="Practice Data", index=False)
            if not export_df.empty:
                group_summary = (
                    export_df.groupby("group", as_index=False)
                    .agg(
                        practices=("workout_id", "nunique"),
                        total_yardage=("total_yardage", "sum"),
                        average_yardage=("total_yardage", "mean"),
                    )
                )
                group_summary.to_excel(writer, sheet_name="Group Summary", index=False)
        st.download_button(
            "Download Excel workbook",
            data=excel_buffer.getvalue(),
            file_name="chssd_swim_season_2026_27.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.caption("Export buttons will appear once practice records have been entered.")


if __name__ == "__main__":
    main()
