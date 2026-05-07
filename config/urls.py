from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("leaguehub.urls")),
    path("login/", auth_views.LoginView.as_view(template_name="leaguehub/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="leaguehub/password_change.html",
            success_url="/password/change/done/",
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="leaguehub/password_change_done.html",
        ),
        name="password_change_done",
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)