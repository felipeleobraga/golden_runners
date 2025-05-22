import requests

class StravaIntegration:
    def __init__(self):
        self.client_id = "SUA_CLIENT_ID"
        self.client_secret = "SEU_CLIENT_SECRET"
        self.redirect_uri = "https://seuapp.com/auth/strava/callback"
        self.auth_url = "https://www.strava.com/oauth/authorize"
        self.token_url = "https://www.strava.com/oauth/token"
        self.activities_url = "https://www.strava.com/api/v3/athlete/activities"

    def get_authorization_url(self):
        return f"{self.auth_url}?client_id={self.client_id}&response_type=code&redirect_uri={self.redirect_uri}&approval_prompt=force&scope=read,activity:read"

    def exchange_code_for_token(self, code):
        response = requests.post(self.token_url, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        })
        return response.json()

    def get_activities(self, access_token):
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.activities_url, headers=headers)
        return response.json()

    def process_activity_for_donation(self, activity):
        km = activity.get("distance", 0) / 1000
        calorias = activity.get("calories", 0)
        doacao = (km * 2.00) + (calorias * 0.01)
        return {"km": km, "calorias": calorias, "doacao": doacao}
