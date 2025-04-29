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
        
    def add_donation_item(self, user_id, title, description, category, location, image_path=None):
        """
        Adiciona um novo item ao mural de doações
        
        Args:
            user_id (str): ID do usuário doador
            title (str): Título do item
            description (str): Descrição do item
            category (str): Categoria do item (ex: 'tênis', 'roupas', 'acessórios')
            location (str): Localização do item (cidade, estado)
            image_path (str, optional): Caminho para a imagem do item
            
        Returns:
            str: ID do item criado
        """
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        item = {
            'id': item_id,
            'user_id': user_id,
            'title': title,
            'description': description,
            'category': category,
            'location': location,
            'image_path': image_path,
            'status': 'available',  # available, reserved, donated
            'created_at': now,
            'updated_at': now
        }
        
        # Em uma implementação real, salvaríamos no banco de dados
        # self.db.insert('donation_items', item)
        
        return item_id
    
    def get_donation_items(self, filters=None, page=1, items_per_page=20):
        """
        Obtém itens do mural de doações com filtros opcionais
        
        Args:
            filters (dict, optional): Filtros a serem aplicados (categoria, status, localização)
            page (int, optional): Página de resultados
            items_per_page (int, optional): Itens por página
            
        Returns:
            dict: Itens de doação e metadados de paginação
        """
        # Em uma implementação real, consultaríamos o banco de dados
        # Simulação de itens para exemplo
        items = [
            {
                'id': '1',
                'user_id': 'user1',
                'title': 'Tênis de Corrida Nike',
                'description': 'Tamanho 42, usado apenas 3 vezes',
                'category': 'tênis',
                'location': 'São Paulo, SP',
                'image_path': '/images/tenis1.jpg',
                'status': 'available',
                'created_at': '2025-04-20T10:30:00',
                'updated_at': '2025-04-20T10:30:00',
                'user': {
                    'name': 'Carlos S.',
                    'profile_image': '/images/user1.jpg'
                }
            },
            {
                'id': '2',
                'user_id': 'user2',
                'title': 'Camiseta Esportiva Adidas',
                'description': 'Tamanho M, nova com etiqueta',
                'category': 'roupas',
                'location': 'Rio de Janeiro, RJ',
                'image_path': '/images/camiseta1.jpg',
                'status': 'available',
                'created_at': '2025-04-21T14:15:00',
                'updated_at': '2025-04-21T14:15:00',
                'user': {
                    'name': 'Ana P.',
                    'profile_image': '/images/user2.jpg'
                }
            },
            {
                'id': '3',
                'user_id': 'user3',
                'title': 'Garrafa Térmica 750ml',
                'description': 'Em ótimo estado, sem arranhões',
                'category': 'acessórios',
                'location': 'Belo Horizonte, MG',
                'image_path': '/images/garrafa1.jpg',
                'status': 'reserved',
                'created_at': '2025-04-19T09:45:00',
                'updated_at': '2025-04-22T16:30:00',
                'user': {
                    'name': 'Marcos T.',
                    'profile_image': '/images/user3.jpg'
                }
            }
        ]
        
        # Aplicar filtros se fornecidos
        if filters:
            filtered_items = []
            for item in items:
                match = True
                
                if 'category' in filters and filters['category'] != 'all':
                    if item['category'] != filters['category']:
                        match = False
                
                if 'status' in filters and filters['status'] != 'all':
                    if item['status'] != filters['status']:
                        match = False
                
                if 'location' in filters and filters['location']:
                    if filters['location'].lower() not in item['location'].lower():
                        match = False
                
                if match:
                    filtered_items.append(item)
            
            items = filtered_items
        
        # Calcular paginação
        total_items = len(items)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        paginated_items = items[start_idx:end_idx]
        
        return {
            'items': paginated_items,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_items': total_items,
                'items_per_page': items_per_page
            }
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
