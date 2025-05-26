from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

main = Blueprint('main', __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/dashboard")
@login_required
def dashboard():
    # Simulação: esses dados podem vir de um serviço, API ou banco
    strava_connected = True  # ou use lógica real de verificação
    strava_activities = [
        {
            "name": "Corrida matinal",
            "start_date": current_user.last_activity,
            "type": "Run",
            "distance": 5000,
            "moving_time": 1500
        }
    ] if strava_connected else []

    return render_template(
        "dashboard.html",
        strava_connected=strava_connected,
        strava_activities=strava_activities
    )

@main.route("/mural")
def mural_page():
    from app.services.donation_service import get_all_items
    from flask import request

    filters = {}
    if "category" in request.args:
        filters["category"] = request.args.get("category")
    if "status" in request.args:
        filters["status"] = request.args.get("status")
    if "location" in request.args:
        filters["location"] = request.args.get("location")

    page = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("items_per_page", 10))

    result = get_all_items(filters=filters, page=page, items_per_page=items_per_page)
    return render_template("mural.html", items=result["items"])