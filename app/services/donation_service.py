from app.core.donation_wall import DonationWallManager
from app.models.db_instance import db

mural = DonationWallManager(db_connector=db)


def get_all_items(filters=None, page=1, items_per_page=20):
    """Retorna itens do mural de doações com filtros e paginação."""
    return mural.get_donation_items(
        filters=filters, page=page, items_per_page=items_per_page
    )


def get_donation_items(filters=None, page=1, items_per_page=20):
    """Alias para :func:`get_all_items`."""
    return get_all_items(filters=filters, page=page, items_per_page=items_per_page)


def get_item_by_id(item_id):
    return mural.get_donation_item(item_id)


def add_new_item(data):
    return mural.add_donation_item(data)


def update_item_status(item_id, status):
    return mural.update_item_status(item_id, status)


def express_interest(item_id, user_data):
    return mural.express_interest(item_id, user_data)


def get_donation_item(item_id):
    return mural.get_donation_item(item_id)
