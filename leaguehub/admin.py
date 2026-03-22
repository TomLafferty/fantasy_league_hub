from django.contrib import admin
from .models import (
    Season,
    ManagerProfile,
    Team,
    Standing,
    Champion,
    Player,
    RosterSnapshot,
    KeeperRecord,
    TeamAccess,
    KeeperSubmission,
)

admin.site.register(Season)
admin.site.register(ManagerProfile)
admin.site.register(Team)
admin.site.register(Standing)
admin.site.register(Champion)
admin.site.register(Player)
admin.site.register(RosterSnapshot)
admin.site.register(KeeperRecord)
admin.site.register(TeamAccess)
admin.site.register(KeeperSubmission)