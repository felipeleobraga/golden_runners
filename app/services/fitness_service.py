from app.core.strava import StravaIntegration
# depois adicionamos Garmin

strava = StravaIntegration()

def get_strava_authorization_url():
    return strava.get_authorization_url()

def handle_strava_callback(code):
    return strava.exchange_code_for_token(code)

def fetch_strava_activities(user_token):
    return strava.get_activities(user_token)

def process_strava_activity(activity):
    return strava.process_activity_for_donation(activity)

from app.core.garmin import GarminIntegration

garmin = GarminIntegration()

def get_garmin_authorization_url():
    return garmin.get_authorization_url()

def handle_garmin_callback(oauth_token, verifier, resource_owner_secret):
    return garmin.exchange_token(oauth_token, verifier, resource_owner_secret)

def fetch_garmin_activities(token, token_secret):
    return garmin.get_activities(token, token_secret)

def process_garmin_activity(activity):
    return garmin.process_activity_for_donation(activity)
