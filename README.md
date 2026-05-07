# Fantasy League Hub

A Django web app for your Yahoo Fantasy Football league — because Yahoo's own website somehow gets worse every year and your league deserves better.

Track historical standings, champions, keeper history, and let managers submit their keeper picks before the draft. Syncs directly from the Yahoo Fantasy API so you don't have to manually enter years of data like some kind of animal.

---

## Features

- **Champions page** — Hall of fame for whoever got lucky that year, complete with league logo per season
- **Standings** — Historical records for every season with the season's logo
- **Keeper history** — Who kept whom, going back as far as Yahoo's API will cooperate
- **Keeper submission** — Managers log in and pick their keepers before the draft. Eligibility enforced automatically (no keeping a player two years in a row). Commissioners and officers can update the deadline directly from the page.
- **Drafts** — Dedicated tab per season. Commissioners/officers post the date, location, and a link (Airbnb, etc.) — the app attempts to pull photos automatically from the URL's Open Graph tags. Any logged-in user can upload media and leave comments. All media is stored on Cloudinary (persistent across deploys).
- **Hottest & Coldest** — Active win/loss streaks with per-game breakdown, calendar days, and average margin. All-time streak records shown at the top.
- **The FFUPA Hall** — Hall of Fame, Hall of Shame, Bro vs Bro head-to-head, Keeper Legends, player stat records, and cumulative all-time points
- **New Rules** — Propose and vote on rule changes. 9 non-official downvotes kills a proposal; commissioner and officer downvotes are exempt from the deletion threshold.
- **Commissioner & Officer roles** — Superuser grants these via the Django admin. Officials can edit the keeper deadline, post draft info, and their votes are privileged.
- **Password change** — Any logged-in user can change their password from the navbar.
- **Yahoo sync** — Pull standings, rosters, metadata, logos, and keeper data directly from Yahoo's API
- **Mobile friendly** — Works on your phone so you can trash talk at the Thanksgiving table
- **Deployable to Render** — Free web tier + Cloudinary for persistent media storage

---

## Requirements

- Python 3.12+
- PostgreSQL
- A Yahoo Fantasy Football league
- A Yahoo Developer account (free) to get API credentials
- A Cloudinary account (free tier) for media uploads
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

# Leave blank locally — uploads will use local disk instead
CLOUDINARY_URL=
```

Generate a secret key with:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **Note on media uploads locally:** When `CLOUDINARY_URL` is blank, uploaded draft photos are stored in `media/` on disk. This is fine for local testing — files won't persist across Render deploys, which is why Cloudinary is used in production.

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

You want a bearer token with `fspt-r` (fantasy sports read) scope.

### Step 2 — Import your leagues from Yahoo

```bash
python manage.py import_yahoo_leagues --access-token "YOUR_TOKEN"
```

This finds all your Yahoo NFL leagues and creates Season records for the ones matching your league name. Update the filter in `leaguehub/management/commands/import_yahoo_leagues.py` to match your league name if it's not F.F.U.P.A.

### Step 3 — Sync all seasons

```bash
python manage.py sync_all_yahoo_seasons --access-token "YOUR_TOKEN" --mark-champions --sync-keepers
```

This pulls for every season that has a Yahoo game key and league key set:
- League metadata (name, logo)
- Standings and team records
- Final rosters (championship week)
- Manager profiles
- Keeper history
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

```bash
python manage.py setup_team_user \
  --season 2025 \
  --team-name "Their Team Name" \
  --username their_username
```

This creates the user (prompts for password), links them to their team via TeamAccess, and connects their ManagerProfile if one was found from Yahoo sync.

---

## Keeper Submission

Once user accounts are set up, managers visit `/keepers/submit/`, log in, and pick up to **2 keepers** from their final roster. The form automatically excludes players who were kept the previous season.

**Setting the deadline:** Commissioners and officers see an "Edit Deadline" button on the Submit Keepers page. No admin access needed.

**Keeper costs:** The form shows the draft round each player was taken in last season. Keeping a player costs the pick from that round. If both keepers came from the same round, you also lose the preceding round's pick.

---

## Commissioner & Officer Roles

Two league-wide role flags live on each manager's profile: `is_commissioner` and `is_officer`. Both grant the same privileges:

- Edit the keeper deadline from `/keepers/submit/`
- Post and edit draft info (date, location, URL, notes) on the Drafts page
- Vote on rule proposals without their downvotes counting toward auto-deletion

**Granting roles:** Log in as a superuser → Django admin → Manager Profiles → edit the manager → check `Is Commissioner` or `Is Officer`.

---

## Drafts Tab

`/drafts/` shows one draft per season, selectable by year.

**Commissioners/officers** can add:
- Draft date
- Location name and URL (Airbnb link, venue website, etc.)
- Notes / announcement text

When a URL is saved, the app attempts to fetch Open Graph images from the page. If it succeeds, photos appear automatically. If not (some sites block scraping), a prompt to upload photos manually appears instead.

**Any logged-in user** can:
- Upload photos or media files (stored persistently on Cloudinary)
- Leave comments

---

## Deployment (Render)

The repo includes a `render.yaml` for one-click deployment.

### Steps

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your GitHub repo
4. In Render → your web service → **Environment**, add:

| Variable | Value |
|---|---|
| `SECRET_KEY` | A long random string |
| `DATABASE_URL` | Set automatically by Render if using their PostgreSQL |
| `ALLOWED_HOSTS` | `your-app.onrender.com` |
| `DEBUG` | `False` |
| `CLOUDINARY_URL` | `cloudinary://API_KEY:API_SECRET@CLOUD_NAME` |

Get your Cloudinary credentials from [cloudinary.com](https://cloudinary.com) → dashboard (free tier is more than enough for a private league).

5. After the first deploy, run setup commands locally against the production database URL (from Render dashboard → your DB → Connect tab):

```bash
export DATABASE_URL="postgres://..."

python manage.py createsuperuser
python manage.py sync_all_yahoo_seasons --access-token "YOUR_TOKEN" --mark-champions --sync-keepers
python manage.py setup_team_user --season 2025 --team-name "Team Name" --username user1
```

### Free tier notes

- The web service **spins down after 15 minutes of inactivity** — first request takes ~30 seconds to wake up. Fine for a private league.
- The free PostgreSQL database **expires after 90 days**. Upgrade to the $7/month plan before it disappears.
- **Cloudinary free tier** includes 25GB storage and bandwidth — more than enough for draft photos forever.
- Render Shell is not available on the free tier, so run management commands locally against the production database URL.

---

## Django Admin

Everything can be managed at `/admin/`. Useful for:
- Manually adding or editing seasons, teams, standings, champions
- Granting commissioner or officer roles to manager profiles
- Linking manager profiles to user accounts
- Setting keeper deadlines (or let commissioners do it from the app)
- Adding keeper records the Yahoo sync missed
- Moderating draft comments or media if needed
- Fixing the inevitable data weirdness from 10+ years of Yahoo API responses

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
│   │                        # KeeperRecord, KeeperSubmission, Draft,
│   │                        # DraftMedia, DraftComment, ManagerProfile,
│   │                        # TeamAccess, RuleProposal, RuleVote, etc.
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
3. **Roster week** — The sync uses Yahoo's `end_week` automatically; override with `--roster-week` if needed
4. **Keeper eligibility rules** — Default rule: no keeping a player kept the previous year. Adjust `KeeperSubmission.clean()` in `models.py` for more complex rules.

---

## Contributing

If you find a bug, open an issue. If you fix a bug, open a pull request. If you're here because you lost your fantasy league and are looking for someone to blame, this is the wrong repo.

---

*Written with [Claude](https://claude.ai) — Anthropic's AI assistant — who spent an unreasonable amount of time debugging Yahoo's Fantasy API response structure so you don't have to. The humans provided the fantasy football domain expertise and the specific grudges against Yahoo's UI.*
