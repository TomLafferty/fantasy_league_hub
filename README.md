# Fantasy League Hub

A Django web app for your Yahoo Fantasy Football league — because Yahoo's own website somehow gets worse every year and your league deserves better.

Track historical standings, champions, keeper history, and let managers submit their keeper picks before the draft. Syncs directly from the Yahoo Fantasy API so you don't have to manually enter years of data like some kind of animal.

---

## Features

- **Champions page** — Hall of fame for whoever got lucky that year, complete with league logo per season
- **Standings** — Historical records for every season, with the season's logo shown when selected
- **Keeper history** — Who kept whom, going back as far as Yahoo's API will cooperate
- **Keeper submission** — Managers log in and pick their keepers before the draft. Eligibility is enforced automatically (no keeping a player two years in a row)
- **Yahoo sync** — Pull standings, rosters, metadata, logos, and keeper data directly from Yahoo's API
- **Mobile friendly** — Works on your phone so you can trash talk at the Thanksgiving table
- **Deployable to Render** — Free tier, no server to babysit

---

## Requirements

- Python 3.12+
- PostgreSQL
- A Yahoo Fantasy Football league
- A Yahoo Developer account (free) to get API credentials
- Mild tolerance for fantasy football arguments

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/fantasy_league_hub.git
cd fantasy_league_hub
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Create a PostgreSQL database

```bash
createdb fantasy_league_hub
```

### 4. Configure environment variables

Copy the example below into a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgres://localhost/fantasy_league_hub
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
```

Generate a secret key with:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Run migrations and create a superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Start the development server

```bash
python manage.py runserver
```

Visit `http://localhost:8000`. You should see the hub. It will be empty — that's normal. Fix it in the next section.

---

## Importing Data from Yahoo

### Step 1 — Get a Yahoo OAuth access token

1. Go to [developer.yahoo.com](https://developer.yahoo.com) and create an app
2. Set the redirect URI to `oob` (out-of-band) for local use
3. Use your `client_id` and `client_secret` to complete the OAuth2 flow and get an access token

There are several Yahoo OAuth helper scripts floating around the internet. You want a bearer token with `fspt-r` (fantasy sports read) scope.

### Step 2 — Import your leagues from Yahoo

This finds all your Yahoo NFL leagues and creates Season records for the ones matching your league name:

```bash
python manage.py import_yahoo_leagues --access-token "YOUR_TOKEN"
```

This only imports leagues with names matching **"F.F.U.P.A."** by default. Update the filter in `leaguehub/management/commands/import_yahoo_leagues.py` to match your own league name.

### Step 3 — Sync all seasons

```bash
python manage.py sync_all_yahoo_seasons --access-token "YOUR_TOKEN" --mark-champions --sync-keepers
```

This pulls for every season that has a Yahoo game key and league key set:
- League metadata (name, logo)
- Standings and team records
- Final rosters (championship week)
- Manager profiles
- Keeper history (tries both draft results and the status=K endpoint)
- Champion (rank 1 team)

To skip the current in-progress season:
```bash
python manage.py sync_all_yahoo_seasons --access-token "YOUR_TOKEN" --skip-current
```

To sync a single season:
```bash
python manage.py sync_yahoo_season --season 2024 --access-token "YOUR_TOKEN" --mark-champion --sync-keepers
```

### Step 4 — Set up user accounts for managers

Each manager who needs to submit keepers needs a Django user account linked to their team:

```bash
python manage.py setup_team_user \
  --season 2025 \
  --team-name "Their Team Name" \
  --username their_username
```

This creates the user (prompts for password), links them to their team via TeamAccess, and connects their ManagerProfile if one was found from Yahoo sync.

---

## Keeper Submission

Once user accounts are set up, managers visit `/keepers/submit/`, log in, and pick up to **2 keepers** from their final roster. The form automatically excludes players who were kept the previous season (no double-dipping).

If a keeper deadline is set on the Season record in the Django admin, the form will show it and reject submissions after the deadline passes.

**Note for offline draft leagues:** Yahoo's API doesn't reliably track keeper history for players who were traded or dropped after being declared keepers. The sync pulls from both draft results and the status=K endpoint to get as much data as possible, but some historical gaps may require manual entry via the Django admin.

---

## Deployment (Render)

The repo includes a `render.yaml` for one-click deployment.

### Steps

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your GitHub repo — Render reads `render.yaml` and provisions the web service and PostgreSQL database automatically
4. After the first deploy, run your sync commands locally pointed at the production database:

```bash
# Get the External Database URL from Render dashboard → your DB → Connect tab
export DATABASE_URL="postgres://..."

python manage.py createsuperuser
python manage.py sync_all_yahoo_seasons --access-token "YOUR_TOKEN" --mark-champions --sync-keepers
python manage.py setup_team_user --season 2025 --team-name "Team Name" --username user1
```

### Free tier notes

- The web service **spins down after 15 minutes of inactivity** — first request takes ~30 seconds to wake up. Fine for a private league.
- The free PostgreSQL database **expires after 90 days**. Upgrade to the $7/month plan before it disappears or you'll lose everything and have to explain it to your league, which will be embarrassing.
- Render Shell is not available on the free tier, which is why you run management commands locally against the production database URL.

---

## Django Admin

Everything can be managed at `/admin/`. Useful for:
- Manually adding or editing seasons, teams, standings, champions
- Setting keeper deadlines
- Adding keeper records that the Yahoo sync missed
- Linking manager profiles to user accounts
- Fixing the inevitable data weirdness that comes from 10+ years of Yahoo API responses

---

## Running Tests

```bash
python manage.py test leaguehub
```

The test suite covers the keeper sync services, including a test that documents the known limitation of `sync_keepers_from_yahoo` when players are traded or dropped mid-season. It's not a bug, it's a feature of Yahoo's API design philosophy.

---

## Project Structure

```
fantasy_league_hub/
├── config/                  # Django project settings, urls, wsgi
├── leaguehub/               # Main app
│   ├── management/commands/ # sync_yahoo_season, sync_all_yahoo_seasons,
│   │                        # import_yahoo_leagues, setup_team_user
│   ├── migrations/
│   ├── templates/leaguehub/
│   ├── models.py            # Season, Team, Standing, Champion, Player,
│   │                        # KeeperRecord, KeeperSubmission, etc.
│   ├── services.py          # Yahoo API sync logic
│   ├── views.py
│   ├── forms.py
│   └── context_processors.py
├── build.sh                 # Render build script
├── render.yaml              # Render deployment config
└── requirements.txt
```

---

## Customizing for Your League

1. **League name filter** — Update `import_yahoo_leagues.py` to match your league name instead of "F.F.U.P.A."
2. **Keeper limit** — Change `max_keepers=2` in `views.py` to however many keepers your league allows
3. **Roster week** — The sync uses Yahoo's `end_week` automatically, but you can override with `--roster-week` if needed
4. **Keeper eligibility rules** — The default rule is "no keeping a player kept the previous year." Adjust `KeeperSubmission.clean()` in `models.py` for more complex rules.

---

## Contributing

If you find a bug, open an issue. If you fix a bug, open a pull request. If you're here because you lost your fantasy league and are looking for someone to blame, this is the wrong repo.

---

*Written by [Claude](https://claude.ai) — Anthropic's AI assistant — who spent an unreasonable amount of time debugging Yahoo's Fantasy API response structure so you don't have to. The humans provided the fantasy football domain expertise and the specific grudges against Yahoo's UI. It was a team effort.*
