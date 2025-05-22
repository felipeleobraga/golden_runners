"""
Módulo para gerenciar o mural de doações do Golden Runners
"""
import os
import uuid
from datetime import datetime

class DonationWallManager:
    """
    Classe para gerenciar o mural de doações
    """
    
    def __init__(self, db_connector):
        """
        Inicializa o gerenciador do mural de doações
        
        Args:
            db_connector: Conector para o banco de dados
        """
        self.db = db_connector
        
from datetime import datetime
import uuid
from app.models.donation_item import DonationItem  # importa o modelo que representa o item no banco

def add_donation_item(self, user_id, title, description, category, location, image_path=None):
    """
    Adiciona um novo item ao mural de doações e salva no banco de dados.

    Args:
        user_id (str): ID do usuário que está doando
        title (str): Título do item
        description (str): Descrição do item
        category (str): Categoria (ex: 'tênis', 'roupas', etc)
        location (str): Cidade e estado do item
        image_path (str): Caminho opcional para a imagem do item

    Returns:
        str: ID único do item criado
    """

    # Gera um ID único para o item
    item_id = str(uuid.uuid4())

    # Captura a data e hora atual
    now = datetime.utcnow()

    # Cria uma instância do modelo DonationItem com os dados recebidos
    new_item = DonationItem(
        id=item_id,
        user_id=user_id,
        title=title,
        description=description,
        category=category,
        location=location,
        image_path=image_path,
        status="available",       # status inicial: disponível
        created_at=now,
        updated_at=now
    )

    # Adiciona a instância à sessão do banco (mas ainda não executa)
    self.db.session.add(new_item)

    # Salva de fato no banco (faz commit da transação)
    self.db.session.commit()

    # Retorna o ID do item recém-criado
    return item_id

    
from app.models.donation_item import DonationItem  # modelo do banco
from sqlalchemy import or_  # opcional se quiser aplicar filtros com OU futuramente

def get_donation_items(self, filters=None, page=1, items_per_page=20):
    """
    Busca itens do mural de doações no banco de dados, com filtros opcionais e paginação.

    Args:
        filters (dict, opcional): Filtros como categoria, status ou location.
        page (int): Página atual dos resultados (padrão: 1)
        items_per_page (int): Quantidade de itens por página (padrão: 20)

    Returns:
        dict: Resultado paginado com os itens:
        {
            "total": int,      # total de resultados encontrados
            "page": int,       # página atual
            "items": [         # lista de dicionários com os itens
                {...}, {...}
            ]
        }
    """

    # Começa uma query base em cima da tabela DonationItem
    query = DonationItem.query

    # Aplica filtros caso tenham sido enviados
    if filters:
        # Filtro por categoria com busca parcial (ex: "%roupa%")
        if "category" in filters:
            query = query.filter(DonationItem.category.ilike(f"%{filters['category']}%"))

        # Filtro por status exato (available, reserved, donated)
        if "status" in filters:
            query = query.filter(DonationItem.status == filters["status"])

        # Filtro por localização (cidade/estado)
        if "location" in filters:
            query = query.filter(DonationItem.location.ilike(f"%{filters['location']}%"))

    # Aplica ordenação por data de criação (mais recentes primeiro)
    # e faz a paginação (LIMIT + OFFSET)
    paginated = query.order_by(DonationItem.created_at.desc()) \
                     .paginate(page=page, per_page=items_per_page, error_out=False)

    # Transforma os objetos em dicionários para retornar no JSON
    items = []
    for item in paginated.items:
        items.append({
            "id": item.id,
            "user_id": item.user_id,
            "title": item.title,
            "description": item.description,
            "category": item.category,
            "location": item.location,
            "image_path": item.image_path,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat()
        })

    # Retorna estrutura com paginação
    return {
        "total": paginated.total,
        "page": paginated.page,
        "items": items
    }

    
    def get_donation_item(self, item_id):
        """
        Obtém detalhes de um item específico
        
        Args:
            item_id (str): ID do item
            
        Returns:
            dict: Detalhes do item ou None se não encontrado
        """
        # Em uma implementação real, consultaríamos o banco de dados
        # Simulação para exemplo
        items = {
            '1': {
                'id': '1',
                'user_id': 'user1',
                'title': 'Tênis de Corrida Nike',
                'description': 'Tamanho 42, usado apenas 3 vezes. Ótimo estado, sem marcas de desgaste. Ideal para corridas de longa distância.',
                'category': 'tênis',
                'location': 'São Paulo, SP',
                'image_path': '/images/tenis1.jpg',
                'status': 'available',
                'created_at': '2025-04-20T10:30:00',
                'updated_at': '2025-04-20T10:30:00',
                'user': {
                    'name': 'Carlos S.',
                    'profile_image': '/images/user1.jpg',
                    'member_since': '2024-10-15',
                    'donation_count': 5
                }
            }
        }
        
        return items.get(item_id)
    
    def update_item_status(self, item_id, status, user_id=None):
        """
        Atualiza o status de um item
        
        Args:
            item_id (str): ID do item
            status (str): Novo status ('available', 'reserved', 'donated')
            user_id (str, optional): ID do usuário que está atualizando (para verificação)
            
        Returns:
            bool: True se atualizado com sucesso, False caso contrário
        """
        # Em uma implementação real, verificaríamos permissões e atualizaríamos no banco de dados
        # Simulação para exemplo
        valid_statuses = ['available', 'reserved', 'donated']
        
        if status not in valid_statuses:
            return False
        
        # Atualizar no banco de dados
        # self.db.update('donation_items', item_id, {'status': status, 'updated_at': datetime.now().isoformat()})
        
        return True
    
    def express_interest(self, item_id, user_id, message):
        """
        Registra interesse de um usuário em um item
        
        Args:
            item_id (str): ID do item
            user_id (str): ID do usuário interessado
            message (str): Mensagem para o doador
            
        Returns:
            str: ID do interesse registrado
        """
        interest_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        interest = {
            'id': interest_id,
            'item_id': item_id,
            'user_id': user_id,
            'message': message,
            'status': 'pending',  # pending, accepted, rejected
            'created_at': now,
            'updated_at': now
        }
        
        # Em uma implementação real, salvaríamos no banco de dados
        # self.db.insert('donation_interests', interest)
        
        return interest_id
    
    def get_user_donation_items(self, user_id):
        """
        Obtém itens doados por um usuário específico
        
        Args:
            user_id (str): ID do usuário
            
        Returns:
            list: Itens doados pelo usuário
        """
        # Em uma implementação real, consultaríamos o banco de dados
        # Simulação para exemplo
        items = [
            {
                'id': '1',
                'title': 'Tênis de Corrida Nike',
                'category': 'tênis',
                'status': 'available',
                'created_at': '2025-04-20T10:30:00',
                'interests_count': 2
            },
            {
                'id': '4',
                'title': 'Mochila de Hidratação',
                'category': 'acessórios',
                'status': 'donated',
                'created_at': '2025-03-15T08:20:00',
                'interests_count': 3
            }
        ]
        
        return items
    
    def get_categories(self):
        """
        Obtém lista de categorias disponíveis
        
        Returns:
            list: Categorias disponíveis
        """
        return [
            {'id': 'tenis', 'name': 'Tênis'},
            {'id': 'roupas', 'name': 'Roupas'},
            {'id': 'acessorios', 'name': 'Acessórios'},
            {'id': 'equipamentos', 'name': 'Equipamentos'},
            {'id': 'eletronicos', 'name': 'Eletrônicos'},
            {'id': 'outros', 'name': 'Outros'}
        ]


# Exemplo de uso
if __name__ == "__main__":
    # Em uma implementação real, teríamos um conector de banco de dados
    db_connector = None
    
    # Inicializar gerenciador
    donation_wall = DonationWallManager(db_connector)
    
    # Obter categorias
    categories = donation_wall.get_categories()
    print("Categorias disponíveis:")
    for category in categories:
        print(f"- {category['name']}")
    
    # Adicionar um item (simulação)
    item_id = donation_wall.add_donation_item(
        user_id="user123",
        title="Tênis de Corrida Asics",
        description="Tamanho 40, usado por 3 meses, em bom estado",
        category="tenis",
        location="Curitiba, PR",
        image_path="/uploads/tenis_asics.jpg"
    )
    print(f"Item adicionado com ID: {item_id}")
    
    # Buscar itens com filtros
    filters = {'category': 'tenis', 'status': 'available'}
    result = donation_wall.get_donation_items(filters, page=1, items_per_page=10)
    
    print(f"Encontrados {result['pagination']['total_items']} itens")
    for item in result['items']:
        print(f"- {item['title']} ({item['location']}) - {item['status']}")
