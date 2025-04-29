"""
Rotas da API para o mural de doações do Golden Runners
"""
from flask import Blueprint, request, jsonify
from donation_wall import DonationWallManager

# Simulação de um conector de banco de dados
db_connector = None

# Inicializar gerenciador do mural de doações
donation_wall = DonationWallManager(db_connector)

# Criar blueprint para as rotas do mural de doações
donation_wall_api = Blueprint('donation_wall_api', __name__)

@donation_wall_api.route('/items', methods=['GET'])
def get_donation_items():
    """
    Obtém itens do mural de doações com filtros opcionais
    """
    # Extrair parâmetros da requisição
    page = int(request.args.get('page', 1))
    items_per_page = int(request.args.get('items_per_page', 20))
    
    # Extrair filtros
    filters = {}
    if 'category' in request.args:
        filters['category'] = request.args.get('category')
    if 'status' in request.args:
        filters['status'] = request.args.get('status')
    if 'location' in request.args:
        filters['location'] = request.args.get('location')
    
    # Obter itens
    result = donation_wall.get_donation_items(filters, page, items_per_page)
    
    return jsonify(result)

@donation_wall_api.route('/items/<item_id>', methods=['GET'])
def get_donation_item(item_id):
    """
    Obtém detalhes de um item específico
    """
    item = donation_wall.get_donation_item(item_id)
    
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    
    return jsonify(item)

@donation_wall_api.route('/items', methods=['POST'])
def add_donation_item():
    """
    Adiciona um novo item ao mural de doações
    """
    # Extrair dados do corpo da requisição
    data = request.json
    
    # Validar dados
    required_fields = ['user_id', 'title', 'description', 'category', 'location']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Campo obrigatório ausente: {field}'}), 400
    
    # Adicionar item
    item_id = donation_wall.add_donation_item(
        user_id=data['user_id'],
        title=data['title'],
        description=data['description'],
        category=data['category'],
        location=data['location'],
        image_path=data.get('image_path')
    )
    
    return jsonify({'id': item_id, 'message': 'Item adicionado com sucesso'}), 201

@donation_wall_api.route('/items/<item_id>/status', methods=['PUT'])
def update_item_status(item_id):
    """
    Atualiza o status de um item
    """
    # Extrair dados do corpo da requisição
    data = request.json
    
    # Validar dados
    if 'status' not in data:
        return jsonify({'error': 'Status não fornecido'}), 400
    
    # Atualizar status
    success = donation_wall.update_item_status(
        item_id=item_id,
        status=data['status'],
        user_id=data.get('user_id')
    )
    
    if not success:
        return jsonify({'error': 'Falha ao atualizar status'}), 400
    
    return jsonify({'message': 'Status atualizado com sucesso'})

@donation_wall_api.route('/items/<item_id>/interest', methods=['POST'])
def express_interest(item_id):
    """
    Registra interesse de um usuário em um item
    """
    # Extrair dados do corpo da requisição
    data = request.json
    
    # Validar dados
    if 'user_id' not in data:
        return jsonify({'error': 'ID do usuário não fornecido'}), 400
    if 'message' not in data:
        return jsonify({'error': 'Mensagem não fornecida'}), 400
    
    # Registrar interesse
    interest_id = donation_wall.express_interest(
        item_id=item_id,
        user_id=data['user_id'],
        message=data['message']
    )
    
    return jsonify({'id': interest_id, 'message': 'Interesse registrado com sucesso'}), 201

@donation_wall_api.route('/categories', methods=['GET'])
def get_categories():
    """
    Obtém lista de categorias disponíveis
    """
    categories = donation_wall.get_categories()
    return jsonify(categories)

@donation_wall_api.route('/user/<user_id>/items', methods=['GET'])
def get_user_donation_items(user_id):
    """
    Obtém itens doados por um usuário específico
    """
    items = donation_wall.get_user_donation_items(user_id)
    return jsonify(items)
