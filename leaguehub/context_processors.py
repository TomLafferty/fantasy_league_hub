from django.core.cache import cache

from .models import Season

_CACHE_KEY = "league_context"
_CACHE_TTL = 300  # 5 minutes


def league_name(request):
    ctx = cache.get(_CACHE_KEY)
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
        cache.set(_CACHE_KEY, ctx, _CACHE_TTL)
    return ctx
