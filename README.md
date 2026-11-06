# CHSSD Swim Season Tracker

A coach-only swim season training log for the 2026–2027 season.

## Features

- Weekly navigation (20 weeks)
- Monday–Friday practice tabs
- Multiple sessions per day
- Multiple training groups sharing a workout
- Group-specific yardage and duration
- Weekly statistics and recap notes
- CSV and Excel exports

## Files

- `app.py`: Streamlit application
- `database.py`: Supabase database operations
- `requirements.txt`: Python dependencies
- `.gitignore`: Excludes local secrets and generated files

## Supabase setup

The Supabase project should contain these tables:

- `weeks`
- `training_groups`
- `workouts`
- `group_workout_entries`

The SQL setup script was run separately in the Supabase SQL Editor.

## Streamlit secrets

In Streamlit Community Cloud, open the app's Settings > Secrets and add:

```toml
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY"
APP_PASSWORD = "YOUR_LONG_UNIQUE_APP_PASSWORD"
```

Keep these values private. Never commit them to GitHub or share them in chat.

The service-role key has elevated database permissions. It is used only server-side by this app and must remain in Streamlit secrets. The app includes a shared-password gate; this is intended for a small private coaching tool, not a public multi-user authentication system.

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this project folder.
3. Create and activate a virtual environment (optional but recommended).
4. Install dependencies:

   `pip install -r requirements.txt`

5. Create `.streamlit/secrets.toml` with the same three settings shown above.
6. Start the app:

   `streamlit run app.py`

## Deploy

1. Push these project files to the private GitHub repository.
2. Create a Streamlit Community Cloud app connected to that repository.
3. Set the main file path to `app.py`.
4. Add the three secrets in the Streamlit app settings.
5. Deploy.

## Data model

A workout is a shared practice/session record. Each training group has its own linked group-workout entry, which stores that group's yardage, duration, set breakdown, and notes.
