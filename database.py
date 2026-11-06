from datetime import date
import streamlit as st
from supabase import create_client


def get_client():
    """Create a Supabase client using server-side Streamlit secrets."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    except Exception as exc:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in Streamlit secrets."
        ) from exc
    return create_client(url, key)


def get_groups(client):
    response = (
        client.table("training_groups")
        .select("*")
        .eq("is_active", True)
        .order("group_name")
        .execute()
    )
    return response.data or []


def get_weeks(client):
    response = (
        client.table("weeks")
        .select("*")
        .order("week_number")
        .execute()
    )
    return response.data or []


def get_week_workouts(client, week_number):
    response = (
        client.table("workouts")
        .select(
            "*, group_workout_entries(*, training_groups(id, group_name))"
        )
        .eq("week_number", week_number)
        .order("practice_date")
        .order("created_at")
        .execute()
    )
    return response.data or []


def get_all_workouts(client):
    response = (
        client.table("workouts")
        .select(
            "*, group_workout_entries(*, training_groups(id, group_name))"
        )
        .order("practice_date")
        .order("created_at")
        .execute()
    )
    return response.data or []


def create_group(client, group_name):
    return (
        client.table("training_groups")
        .insert({"group_name": group_name, "is_active": True})
        .execute()
    )


def create_workout(
    week_number,
    practice_date,
    day,
    session_name,
    description,
    general_notes,
    group_values,
    is_no_practice=False,
):
    client = get_client()
    workout_response = (
        client.table("workouts")
        .insert({
            "week_number": int(week_number),
            "practice_date": practice_date.isoformat()
            if isinstance(practice_date, date)
            else str(practice_date),
            "day_of_week": day,
            "session_name": session_name,
            "workout_description": description,
            "general_notes": general_notes,
            "is_no_practice": bool(is_no_practice),
        })
        .execute()
    )
    if not workout_response.data:
        raise RuntimeError("The workout was not returned after creation.")

    workout_id = workout_response.data[0]["id"]
    entries = [
        {
            "workout_id": workout_id,
            "group_id": item["group_id"],
            "total_yardage": int(item.get("total_yardage", 0)),
            "duration_minutes": int(item.get("duration_minutes", 0)),
            "practice_type": item.get("practice_type"),
        }
        for item in group_values
    ]
    if entries:
        client.table("group_workout_entries").insert(entries).execute()
    return workout_id


def update_workout(workout_id, values):
    client = get_client()
    return (
        client.table("workouts")
        .update(values)
        .eq("id", workout_id)
        .execute()
    )


def delete_workout(workout_id):
    client = get_client()
    return (
        client.table("workouts")
        .delete()
        .eq("id", workout_id)
        .execute()
    )


def save_group_entry(workout_id, group_id, values, entry_id=None):
    client = get_client()
    payload = {
        "workout_id": workout_id,
        "group_id": group_id,
        **values,
    }
    if entry_id:
        return (
            client.table("group_workout_entries")
            .update(payload)
            .eq("id", entry_id)
            .execute()
        )
    return client.table("group_workout_entries").insert(payload).execute()


def delete_group_entry(entry_id):
    client = get_client()
    return (
        client.table("group_workout_entries")
        .delete()
        .eq("id", entry_id)
        .execute()
    )


def update_week(week_number, values):
    client = get_client()
    return (
        client.table("weeks")
        .update(values)
        .eq("week_number", int(week_number))
        .execute()
    )
