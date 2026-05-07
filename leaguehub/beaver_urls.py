from django.urls import path

from .beaver_views import (
    beaver_home,
    beaver_standings,
    beaver_rosters,
    beaver_transactions,
    beaver_picks,
    beaver_drafts,
    beaver_hall,
    beaver_hottest,
)

urlpatterns = [
    path("",              beaver_home,         name="beaver_home"),
    path("standings/",    beaver_standings,    name="beaver_standings"),
    path("rosters/",      beaver_rosters,      name="beaver_rosters"),
    path("transactions/", beaver_transactions, name="beaver_transactions"),
    path("picks/",        beaver_picks,        name="beaver_picks"),
    path("drafts/",       beaver_drafts,       name="beaver_drafts"),
    path("hall/",         beaver_hall,         name="beaver_hall"),
    path("hottest/",      beaver_hottest,      name="beaver_hottest"),
]
