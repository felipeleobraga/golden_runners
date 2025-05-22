from app.core.donation_wall import DonationWallManager
from app.models.user import db
from app.models.donation_item import DonationItem


mural = DonationWallManager(db_connector=db)

def get_all_items():
    return mural.get_donation_items()

def get_item_by_id(item_id):
    return mural.get_donation_item(item_id)

def add_new_item(data):
    return mural.add_donation_item(data)

def update_item_status(item_id, status):
    return mural.update_item_status(item_id, status)

def express_interest(item_id, user_data):
    return mural.express_interest(item_id, user_data)

def get_donation_item(self, item_id):
    return mural.get_donation_item(item_id)

    """
    Retorna os detalhes de um item do mural de doações, a partir do banco.

    Args:
        item_id (str): ID do item

    Returns:
        dict | None: Detalhes do item ou None se não encontrado
    """
    # Consulta o banco usando SQLAlchemy
    item = DonationItem.query.get(item_id)

    # Se não encontrar, retorna None
    if not item:
        return None

    # Transforma o objeto em dicionário para retorno via API
    return {
        "id": item.id,
        "user_id": item.user_id,
        "title": item.title,
        "description": item.description,
        "category": item.category,
        "location": item.location,
        "image_path": item.image_path,
        "image_url": item.image_path,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat()

    }


