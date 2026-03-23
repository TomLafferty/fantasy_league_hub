from .models import Season


def league_name(request):
    season = Season.objects.filter(is_current=True).first()
    if not season:
        season = Season.objects.order_by("-year").first()
    if season and season.name:
        parts = season.name.split(" ", 1)
        name = parts[1] if len(parts) == 2 else season.name
    else:
        name = "F.F.U.P.A."
    logo_url = season.logo_url if season else ""
    return {"league_name": name, "league_logo_url": logo_url}
