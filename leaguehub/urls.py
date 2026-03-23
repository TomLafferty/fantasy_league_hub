from django.urls import path
from .views import (
    home,
    champions_view,
    standings_view,
    keeper_history_view,
    submit_keepers_view,
    team_detail_view,
)

urlpatterns = [
    path("", home, name="home"),
    path("champions/", champions_view, name="champions"),
    path("standings/", standings_view, name="standings"),
    path("keepers/history/", keeper_history_view, name="keeper_history"),
    path("keepers/submit/", submit_keepers_view, name="submit_keepers"),
    path("team/<int:team_id>/", team_detail_view, name="team_detail"),
]