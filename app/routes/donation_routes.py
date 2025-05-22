from flask import Blueprint, request, jsonify
from app.services.donation_service import (
    get_all_items,
    get_item_by_id,
    add_new_item,
    update_item_status,
    express_interest,
    get_donation_item
)

donation = Blueprint("donation", __name__)

@donation.route("/items", methods=["GET"])
def list_items():
    return jsonify(get_all_items())

@donation.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    return jsonify(get_item_by_id(item_id))

@donation.route("/items", methods=["POST"])
def create_item():
    data = request.json
    return jsonify(add_new_item(data)), 201

@donation.route("/items/<int:item_id>/status", methods=["PUT"])
def update_status(item_id):
    data = request.json
    status = data.get("status")
    return jsonify(update_item_status(item_id, status))

@donation.route("/items/<int:item_id>/interest", methods=["POST"])
def register_interest(item_id):
    user_data = request.json
    return jsonify(express_interest(item_id, user_data))

@donation.route("/donations", methods=["GET"])
def list_donations():
    """
    Retorna uma lista paginada de doações com filtros opcionais.

    Query Params:
      - category: categoria do item (ex: roupas)
      - status: status do item (available, reserved, donated)
      - location: localização parcial (ex: São Paulo)
      - page: página (padrão 1)
      - items_per_page: limite por página (padrão 20)

    Returns:
      JSON com lista paginada de doações
    """
    # Captura os filtros enviados pela URL
    filters = {}
    if "category" in request.args:
        filters["category"] = request.args.get("category")

    if "status" in request.args:
        filters["status"] = request.args.get("status")

    if "location" in request.args:
        filters["location"] = request.args.get("location")

    # Pega os parâmetros de paginação (ou usa os padrões)
    page = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("items_per_page", 20))

    # Consulta os itens no serviço
    result = get_donation_items(filters=filters, page=page, items_per_page=items_per_page)

    return jsonify(result), 200

@donation.route("/donations/<string:item_id>", methods=["GET"])
def get_donation_by_id(item_id):
    """
    Retorna os detalhes de um item de doação específico, via ID.
    """
    item = get_donation_item(item_id)

    if not item:
        return jsonify({"error": "Item não encontrado"}), 404

    return jsonify(item), 200


