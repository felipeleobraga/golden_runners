import requests
from requests_oauthlib import OAuth1Session

class GarminIntegration:
    def __init__(self):
        self.consumer_key = "SEU_CONSUMER_KEY"
        self.consumer_secret = "SEU_CONSUMER_SECRET"
        self.request_token_url = "https://api.garmin.com/oauth-service/oauth/request_token"
        self.authorization_url = "https://connect.garmin.com/oauthConfirm"
        self.access_token_url = "https://api.garmin.com/oauth-service/oauth/access_token"
        self.activities_url = "https://api.garmin.com/fitness-api/activities"

    def get_authorization_url(self):
        oauth = OAuth1Session(self.consumer_key, client_secret=self.consumer_secret)
        fetch_response = oauth.fetch_request_token(self.request_token_url)
        resource_owner_key = fetch_response.get('oauth_token')
        resource_owner_secret = fetch_response.get('oauth_token_secret')

        authorization_url = oauth.authorization_url(self.authorization_url)
        return {
            "authorization_url": authorization_url,
            "oauth_token": resource_owner_key,
            "oauth_token_secret": resource_owner_secret
        }

    def exchange_token(self, oauth_token, oauth_verifier, resource_owner_secret):
        oauth = OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=oauth_token,
            resource_owner_secret=resource_owner_secret,
            verifier=oauth_verifier,
        )
        oauth_tokens = oauth.fetch_access_token(self.access_token_url)
        return oauth_tokens

    def get_activities(self, token, token_secret):
        oauth = OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=token,
            resource_owner_secret=token_secret,
        )
        response = oauth.get(self.activities_url)
        return response.json()

    def process_activity_for_donation(self, activity):
        km = activity.get("distance", 0) / 1000
        calorias = activity.get("calories", 0)
        doacao = (km * 2.00) + (calorias * 0.01)
        return {"km": km, "calorias": calorias, "doacao": doacao}
