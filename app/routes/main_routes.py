from flask import Blueprint, render_template, request
from app.services.donation_service import get_all_items

main = Blueprint('main', __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/teams/join")
def join_team():
    return "Página de inscrição em time"

@main.route("/mural")
def mural_page():
    # Captura filtros da URL (ex: ?category=tênis&page=2)
    filters = {}
    if "category" in request.args:
        filters["category"] = request.args.get("category")

    if "status" in request.args:
        filters["status"] = request.args.get("status")

    if "location" in request.args:
        filters["location"] = request.args.get("location")

    page = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("items_per_page", 10))

    # Chama o serviço para buscar os dados do banco
    result = get_donation_items(filters=filters, page=page, items_per_page=items_per_page)

    # Envia a lista de itens para o template
    return render_template("mural.html", items=result["items"])
