from flask import Blueprint, request, jsonify
from app.services.fitness_service import (
    get_strava_authorization_url,
    handle_strava_callback,
    fetch_strava_activities,
    process_strava_activity,
    get_garmin_authorization_url,
    handle_garmin_callback,
    fetch_garmin_activities,
    process_garmin_activity,
)

fitness = Blueprint("fitness", __name__)

@fitness.route("/auth/strava", methods=["GET"])
def authorize_strava():
    return jsonify({"url": get_strava_authorization_url()})

@fitness.route("/auth/strava/callback", methods=["GET"])
def callback_strava():
    code = request.args.get("code")
    tokens = handle_strava_callback(code)
    return jsonify(tokens)

@fitness.route("/strava/activities", methods=["GET"])
def activities():
    access_token = request.headers.get("Authorization", "").replace("Bearer ", "")
    activities = fetch_strava_activities(access_token)
    processed = [process_strava_activity(a) for a in activities]
    return jsonify(processed)

@fitness.route("/auth/garmin", methods=["GET"])
def authorize_garmin():
    return jsonify(get_garmin_authorization_url())

@fitness.route("/auth/garmin/callback", methods=["POST"])
def callback_garmin():
    data = request.json
    oauth_token = data.get("oauth_token")
    verifier = data.get("oauth_verifier")
    resource_owner_secret = data.get("oauth_token_secret")
    tokens = handle_garmin_callback(oauth_token, verifier, resource_owner_secret)
    return jsonify(tokens)

@fitness.route("/garmin/activities", methods=["POST"])
def garmin_activities():
    data = request.json
    token = data.get("token")
    token_secret = data.get("token_secret")
    activities = fetch_garmin_activities(token, token_secret)
    processed = [process_garmin_activity(a) for a in activities]
    return jsonify(processed)
