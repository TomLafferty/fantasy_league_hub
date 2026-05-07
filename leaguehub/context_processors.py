from django.core.cache import cache

from .models import Season, SleeperLeague

_FFUPA_CACHE_KEY = "league_context_ffupa"
_CACHE_TTL = 300  # 5 minutes


def league_context(request):
    active_hub = "beaver" if request.path.startswith("/beaver/") else "ffupa"

    ctx = cache.get(_FFUPA_CACHE_KEY)
    if ctx is None:
        season = Season.objects.filter(is_current=True).first()
        if not season:
            season = Season.objects.order_by("-year").first()
        if season and season.name:
            parts = season.name.split(" ", 1)
            name = parts[1] if len(parts) == 2 else season.name
        else:
            name = "F.F.U.P.A."
        ctx = {"league_name": name, "league_logo_url": season.logo_url if season else ""}
        cache.set(_FFUPA_CACHE_KEY, ctx, _CACHE_TTL)

    sleeper_league = SleeperLeague.objects.filter(is_current=True).first()

    return {
        **ctx,
        "active_hub": active_hub,
        "sleeper_league": sleeper_league,
    }
