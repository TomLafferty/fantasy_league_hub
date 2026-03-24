#!/bin/bash
# Full Yahoo sync for all seasons.
# Usage: TOKEN="your_token_here" bash sync_all.sh
# Or:    export TOKEN="your_token_here" && bash sync_all.sh

set -e

if [ -z "$TOKEN" ]; then
  echo "ERROR: TOKEN is not set. Run as: TOKEN='...' bash sync_all.sh"
  exit 1
fi

PY="python manage.py"

# ── 2018 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2018 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2018 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2018 --access-token "$TOKEN" && \

# ── 2019 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2019 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2019 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2019 --access-token "$TOKEN" && \

# ── 2020 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2020 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2020 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2020 --access-token "$TOKEN" && \

# ── 2021 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2021 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2021 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2021 --access-token "$TOKEN" && \

# ── 2022 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2022 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2022 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2022 --access-token "$TOKEN" && \

# ── 2023 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2023 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2023 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2023 --access-token "$TOKEN" && \

# ── 2024 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2024 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2024 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2024 --access-token "$TOKEN" && \

# ── 2025 ────────────────────────────────────────────────────────────────────
$PY sync_yahoo_season   --season 2025 --access-token "$TOKEN" --sync-keepers --mark-champion && \
$PY sync_matchups       --season 2025 --access-token "$TOKEN" && \
$PY sync_player_scores  --season 2025 --access-token "$TOKEN"

echo "All seasons synced."
