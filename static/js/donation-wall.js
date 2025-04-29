"""
Componente JavaScript para o mural de doações do Golden Runners
"""

// Componente principal do mural de doações
class DonationWall {
  constructor() {
    this.apiBaseUrl = '/api/donation-wall';
    this.currentPage = 1;
    this.currentFilters = {
      category: 'all',
      status: 'available'
    };
    this.itemsPerPage = 12;
  }

  // Inicializa o mural de doações
  init() {
    this.loadCategories();
    this.setupEventListeners();
    this.loadItems();
  }

  // Carrega as categorias disponíveis
  async loadCategories() {
    try {
      const response = await fetch(`${this.apiBaseUrl}/categories`);
      const categories = await response.json();
      
      const categoryFilter = document.getElementById('category-filter');
      if (categoryFilter) {
        // Adicionar opção "Todos"
        let html = '<button class="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded-full text-sm font-medium" data-category="all">Todos</button>';
        
        // Adicionar categorias
        categories.forEach(category => {
          html += `<button class="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded-full text-sm font-medium" data-category="${category.id}">${category.name}</button>`;
        });
        
        categoryFilter.innerHTML = html;
        
        // Adicionar event listeners
        const categoryButtons = categoryFilter.querySelectorAll('button');
        categoryButtons.forEach(button => {
          button.addEventListener('click', () => {
            // Remover classe ativa de todos os botões
            categoryButtons.forEach(btn => {
              btn.classList.remove('bg-yellow-500', 'text-black');
              btn.classList.add('bg-gray-200', 'text-gray-800');
            });
            
            // Adicionar classe ativa ao botão clicado
            button.classList.remove('bg-gray-200', 'text-gray-800');
            button.classList.add('bg-yellow-500', 'text-black');
            
            // Atualizar filtro e carregar itens
            this.currentFilters.category = button.dataset.category;
            this.currentPage = 1;
            this.loadItems();
          });
        });
        
        // Ativar botão "Todos" por padrão
        categoryButtons[0].click();
      }
    } catch (error) {
      console.error('Erro ao carregar categorias:', error);
    }
  }

  // Configura os event listeners
  setupEventListeners() {
    // Event listener para o botão de adicionar item
    const addItemButton = document.getElementById('add-item-button');
    if (addItemButton) {
      addItemButton.addEventListener('click', () => {
        this.showAddItemModal();
      });
    }
    
    // Event listener para o campo de busca por localização
    const locationSearch = document.getElementById('location-search');
    if (locationSearch) {
      locationSearch.addEventListener('input', () => {
        this.currentFilters.location = locationSearch.value;
        this.debounce(() => {
          this.currentPage = 1;
          this.loadItems();
        }, 500)();
      });
    }
    
    // Event listeners para paginação
    const prevPageButton = document.getElementById('prev-page');
    const nextPageButton = document.getElementById('next-page');
    
    if (prevPageButton) {
      prevPageButton.addEventListener('click', () => {
        if (this.currentPage > 1) {
          this.currentPage--;
          this.loadItems();
        }
      });
    }
    
    if (nextPageButton) {
      nextPageButton.addEventListener('click', () => {
        this.currentPage++;
        this.loadItems();
      });
    }
  }

  // Carrega os itens do mural de doações
  async loadItems() {
    try {
      const itemsContainer = document.getElementById('donation-items');
      if (!itemsContainer) return;
      
      // Mostrar indicador de carregamento
      itemsContainer.innerHTML = '<div class="col-span-full text-center py-12"><div class="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-yellow-500"></div><p class="mt-2 text-gray-600">Carregando itens...</p></div>';
      
      // Construir URL com filtros e paginação
      let url = `${this.apiBaseUrl}/items?page=${this.currentPage}&items_per_page=${this.itemsPerPage}`;
      
      if (this.currentFilters.category && this.currentFilters.category !== 'all') {
        url += `&category=${this.currentFilters.category}`;
      }
      
      if (this.currentFilters.status) {
        url += `&status=${this.currentFilters.status}`;
      }
      
      if (this.currentFilters.location) {
        url += `&location=${this.currentFilters.location}`;
      }
      
      const response = await fetch(url);
      const result = await response.json();
      
      // Atualizar paginação
      this.updatePagination(result.pagination);
      
      // Renderizar itens
      if (result.items.length === 0) {
        itemsContainer.innerHTML = '<div class="col-span-full text-center py-12"><p class="text-gray-600">Nenhum item encontrado com os filtros selecionados.</p></div>';
        return;
      }
      
      let html = '';
      result.items.forEach(item => {
        html += this.renderItemCard(item);
      });
      
      itemsContainer.innerHTML = html;
      
      // Adicionar event listeners para botões de interesse
      const interestButtons = itemsContainer.querySelectorAll('.interest-button');
      interestButtons.forEach(button => {
        button.addEventListener('click', () => {
          const itemId = button.dataset.itemId;
          this.showInterestModal(itemId);
        });
      });
    } catch (error) {
      console.error('Erro ao carregar itens:', error);
      const itemsContainer = document.getElementById('donation-items');
      if (itemsContainer) {
        itemsContainer.innerHTML = '<div class="col-span-full text-center py-12"><p class="text-red-600">Erro ao carregar itens. Por favor, tente novamente.</p></div>';
      }
    }
  }

  // Renderiza um card de item
  renderItemCard(item) {
    let statusBadge = '';
    let actionButton = '';
    
    // Definir badge de status
    if (item.status === 'available') {
      statusBadge = '<span class="absolute top-2 right-2 bg-green-500 text-white text-xs font-bold px-2 py-1 rounded">Disponível</span>';
      actionButton = `<a href="#" class="bg-black hover:bg-gray-800 text-white text-sm font-bold py-2 px-4 rounded-full w-full block text-center interest-button" data-item-id="${item.id}">Tenho Interesse</a>`;
    } else if (item.status === 'reserved') {
      statusBadge = '<span class="absolute top-2 right-2 bg-yellow-500 text-white text-xs font-bold px-2 py-1 rounded">Reservado</span>';
      actionButton = '<button disabled class="bg-gray-300 text-gray-600 text-sm font-bold py-2 px-4 rounded-full w-full block text-center cursor-not-allowed">Reservado</button>';
    } else if (item.status === 'donated') {
      statusBadge = '<span class="absolute top-2 right-2 bg-red-500 text-white text-xs font-bold px-2 py-1 rounded">Doado</span>';
      actionButton = '<button disabled class="bg-gray-300 text-gray-600 text-sm font-bold py-2 px-4 rounded-full w-full block text-center cursor-not-allowed">Doado</button>';
    }
    
    return `
      <div class="bg-white rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow duration-300">
        <div class="h-48 bg-gray-200 relative" style="background-image: url('${item.image_path || '/images/placeholder.jpg'}'); background-size: cover; background-position: center;">
          ${statusBadge}
        </div>
        <div class="p-4">
          <h3 class="font-bold text-lg mb-1">${item.title}</h3>
          <p class="text-gray-600 text-sm mb-2">${item.description}</p>
          <div class="flex justify-between items-center">
            <div class="flex items-center">
              <img src="${item.user?.profile_image || '/images/user-placeholder.jpg'}" alt="User" class="h-6 w-6 rounded-full mr-2">
              <span class="text-xs text-gray-500">${item.user?.name || 'Usuário'}</span>
            </div>
            <span class="text-xs text-gray-500">${item.location}</span>
          </div>
          <div class="mt-4">
            ${actionButton}
          </div>
        </div>
      </div>
    `;
  }

  // Atualiza a paginação
  updatePagination(pagination) {
    const paginationContainer = document.getElementById('pagination');
    if (!paginationContainer) return;
    
    const { current_page, total_pages } = pagination;
    
    // Atualizar texto da página atual
    const currentPageElement = document.getElementById('current-page');
    if (currentPageElement) {
      currentPageElement.textContent = current_page;
    }
    
    // Atualizar estado dos botões de paginação
    const prevPageButton = document.getElementById('prev-page');
    const nextPageButton = document.getElementById('next-page');
    
    if (prevPageButton) {
      if (current_page <= 1) {
        prevPageButton.classList.add('opacity-50', 'cursor-not-allowed');
      } else {
        prevPageButton.classList.remove('opacity-50', 'cursor-not-allowed');
      }
    }
    
    if (nextPageButton) {
      if (current_page >= total_pages) {
        nextPageButton.classList.add('opacity-50', 'cursor-not-allowed');
      } else {
        nextPageButton.classList.remove('opacity-50', 'cursor-not-allowed');
      }
    }
  }

  // Exibe o modal para adicionar um novo item
  showAddItemModal() {
    // Implementação do modal para adicionar item
    const modal = document.getElementById('add-item-modal');
    if (!modal) return;
    
    // Exibir modal
    modal.classList.remove('hidden');
    
    // Configurar event listener para o formulário
    const form = modal.querySelector('form');
    if (form) {
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        
        // Obter dados do formulário
        const formData = new FormData(form);
        const data = {
          user_id: this.getCurrentUserId(), // Função para obter ID do usuário atual
          title: formData.get('title'),
          description: formData.get('description'),
          category: formData.get('category'),
          location: formData.get('location'),
          image_path: formData.get('image') ? '/uploads/' + formData.get('image').name : null
        };
        
        try {
          // Enviar dados para a API
          const response = await fetch(`${this.apiBaseUrl}/items`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
          });
          
          if (response.ok) {
            // Fechar modal e recarregar itens
            this.closeModal(modal);
            this.loadItems();
            this.showNotification('Item adicionado com sucesso!', 'success');
          } else {
            const error = await response.json();
            this.showNotification(error.error || 'Erro ao adicionar item', 'error');
          }
        } catch (error) {
          console.error('Erro ao adicionar item:', error);
          this.showNotification('Erro ao adicionar item. Por favor, tente novamente.', 'error');
        }
      });
    }
    
    // Configurar event listener para fechar o modal
    const closeButton = modal.querySelector('.close-modal');
    if (closeButton) {
      closeButton.addEventListener('click', () => {
        this.closeModal(modal);
      });
    }
  }

  // Exibe o modal para expressar interesse em um item
  showInterestModal(itemId) {
    // Implementação do modal para expressar interesse
    const modal = document.getElementById('interest-modal');
    if (!modal) return;
    
    // Exibir modal
    modal.classList.remove('hidden');
    
    // Configurar event listener para o formulário
    const form = modal.querySelector('form');
    if (form) {
      form.dataset.itemId = itemId;
      
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        
        // Obter dados do formulário
        const formData = new FormData(form);
        const data = {
          user_id: this.getCurrentUserId(), // Função para obter ID do usuário atual
          message: formData.get('message')
        };
        
        try {
          // Enviar dados para a API
          const response = await fetch(`${this.apiBaseUrl}/items/${itemId}/interest`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
          });
          
          if (response.ok) {
            // Fechar modal e recarregar itens
            this.closeModal(modal);
            this.loadItems();
            this.showNotification('Interesse registrado com sucesso!', 'success');
          } else {
            const error = await response.json();
            this.showNotification(error.error || 'Erro ao registrar interesse', 'error');
          }
        } catch (error) {
          console.error('Erro ao registrar interesse:', error);
          this.showNotification('Erro ao registrar interesse. Por favor, tente novamente.', 'error');
        }
      });
    }
    
    // Configurar event listener para fechar o modal
    const closeButton = modal.querySelector('.close-modal');
    if (closeButton) {
      closeButton.addEventListener('click', () => {
        this.closeModal(modal);
      });
    }
  }

  // Fecha um modal
  closeModal(modal) {
    modal.classList.add('hidden');
    
    // Resetar formulário
    const form = modal.querySelector('form');
    if (form) {
      form.reset();
    }
  }

  // Exibe uma notificação
  showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg ${type === 'error' ? 'bg-red-500' : 'bg-green-500'} text-white`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Remover notificação após 3 segundos
    setTimeout(() => {
      notification.remove();
    }, 3000);
  }

  // Função para debounce
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Obtém o ID do usuário atual
  getCurrentUserId() {
    // Em uma implementação real, isso viria do sistema de autenticação
    return 'current_user_id';
  }
}

// Inicializar o mural de doações quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
  const donationWall = new DonationWall();
  donationWall.init();
});
