import os
import requests
from requests.auth import HTTPBasicAuth
from django.core.exceptions import ImproperlyConfigured

_REQUIRED_ENV_VARS = ("YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET", "YAHOO_REDIRECT_URI")


class YahooOAuthClient:
    AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
    TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
    API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

    def __init__(self):
        missing = [k for k in _REQUIRED_ENV_VARS if not os.environ.get(k)]
        if missing:
            raise ImproperlyConfigured(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )
        self.client_id = os.environ["YAHOO_CLIENT_ID"]
        self.client_secret = os.environ["YAHOO_CLIENT_SECRET"]
        self.redirect_uri = os.environ["YAHOO_REDIRECT_URI"]

    def build_auth_url(self, state: str, scope: str = "fspt-r") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope,
            "language": "en-us",
            "state": state,
        }
        return requests.Request("GET", self.AUTH_URL, params=params).prepare().url

    def exchange_code(self, code: str) -> dict:
        response = requests.post(
            self.TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "redirect_uri": self.redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get(self, access_token: str, path: str, params=None) -> dict:
        response = requests.get(
            f"{self.API_BASE}/{path}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            params=params or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()