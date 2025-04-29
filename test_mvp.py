"""
Script de teste para o MVP do Golden Runners
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Adicionar diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar módulos a serem testados
from donation_wall import DonationWallManager
from strava_integration import StravaIntegration
from garmin_integration import GarminIntegration
from fitness_integration_manager import FitnessIntegrationManager

class TestDonationWall(unittest.TestCase):
    """Testes para o mural de doações"""
    
    def setUp(self):
        """Configuração inicial para os testes"""
        self.db_connector = MagicMock()
        self.donation_wall = DonationWallManager(self.db_connector)
    
    def test_add_donation_item(self):
        """Testa a adição de um item ao mural de doações"""
        item_id = self.donation_wall.add_donation_item(
            user_id="test_user",
            title="Tênis de Corrida",
            description="Tamanho 42, pouco uso",
            category="tenis",
            location="São Paulo, SP"
        )
        
        # Verificar se o ID foi gerado
        self.assertIsNotNone(item_id)
        self.assertTrue(isinstance(item_id, str))
    
    def test_get_donation_items(self):
        """Testa a obtenção de itens do mural de doações"""
        result = self.donation_wall.get_donation_items()
        
        # Verificar se o resultado tem a estrutura esperada
        self.assertIn('items', result)
        self.assertIn('pagination', result)
        self.assertIn('current_page', result['pagination'])
        self.assertIn('total_pages', result['pagination'])
    
    def test_get_donation_items_with_filters(self):
        """Testa a obtenção de itens com filtros"""
        filters = {'category': 'tenis', 'status': 'available'}
        result = self.donation_wall.get_donation_items(filters)
        
        # Verificar se o resultado tem a estrutura esperada
        self.assertIn('items', result)
        self.assertIn('pagination', result)
    
    def test_update_item_status(self):
        """Testa a atualização de status de um item"""
        # Testar com status válido
        result = self.donation_wall.update_item_status('1', 'reserved')
        self.assertTrue(result)
        
        # Testar com status inválido
        result = self.donation_wall.update_item_status('1', 'invalid_status')
        self.assertFalse(result)
    
    def test_express_interest(self):
        """Testa o registro de interesse em um item"""
        interest_id = self.donation_wall.express_interest(
            item_id='1',
            user_id='test_user',
            message='Tenho interesse neste item'
        )
        
        # Verificar se o ID foi gerado
        self.assertIsNotNone(interest_id)
        self.assertTrue(isinstance(interest_id, str))


class TestStravaIntegration(unittest.TestCase):
    """Testes para a integração com Strava"""
    
    def setUp(self):
        """Configuração inicial para os testes"""
        self.strava = StravaIntegration(
            client_id='test_client_id',
            client_secret='test_client_secret',
            redirect_uri='https://example.com/callback'
        )
    
    def test_get_authorization_url(self):
        """Testa a geração da URL de autorização"""
        auth_url = self.strava.get_authorization_url()
        
        # Verificar se a URL contém os parâmetros esperados
        self.assertIn('client_id=test_client_id', auth_url)
        self.assertIn('redirect_uri=', auth_url)
        self.assertIn('scope=', auth_url)
    
    @patch('requests.post')
    def test_exchange_code_for_token(self, mock_post):
        """Testa a troca de código por token"""
        # Configurar mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'expires_at': 1619395200
        }
        mock_post.return_value = mock_response
        
        # Chamar método
        result = self.strava.exchange_code_for_token('test_code')
        
        # Verificar resultado
        self.assertEqual(result['access_token'], 'test_access_token')
        self.assertEqual(result['refresh_token'], 'test_refresh_token')
    
    @patch('requests.get')
    def test_get_activities(self, mock_get):
        """Testa a obtenção de atividades"""
        # Configurar mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 1234567890,
                'type': 'Run',
                'distance': 5000,
                'calories': 450,
                'start_date': '2025-04-20T07:30:00Z'
            }
        ]
        mock_get.return_value = mock_response
        
        # Chamar método
        activities = self.strava.get_activities('test_access_token')
        
        # Verificar resultado
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]['id'], 1234567890)
    
    def test_process_activity_for_donation(self):
        """Testa o processamento de atividade para doação"""
        activity = {
            'id': 1234567890,
            'type': 'Run',
            'distance': 5000,  # 5 km
            'calories': 450,
            'start_date': '2025-04-20T07:30:00Z'
        }
        
        result = self.strava.process_activity_for_donation(
            activity,
            donation_rate_per_km=2.0,
            donation_rate_per_calorie=0.01
        )
        
        # Verificar cálculo da doação
        # 5 km * R$ 2,00 + 450 cal * R$ 0,01 = R$ 10,00 + R$ 4,50 = R$ 14,50
        self.assertEqual(result['donation_amount'], 14.5)


class TestFitnessIntegrationManager(unittest.TestCase):
    """Testes para o gerenciador de integrações de fitness"""
    
    def setUp(self):
        """Configuração inicial para os testes"""
        self.config = {
            'strava': {
                'client_id': 'test_strava_client_id',
                'client_secret': 'test_strava_client_secret',
                'redirect_uri': 'https://example.com/strava/callback'
            },
            'garmin': {
                'consumer_key': 'test_garmin_consumer_key',
                'consumer_secret': 'test_garmin_consumer_secret',
                'redirect_uri': 'https://example.com/garmin/callback'
            },
            'donation_rates': {
                'km': 2.0,
                'calorie': 0.01
            }
        }
        
        self.manager = FitnessIntegrationManager(self.config)
    
    def test_get_authorization_url(self):
        """Testa a obtenção de URLs de autorização"""
        # Testar para Strava
        strava_url = self.manager.get_authorization_url('strava')
        self.assertIn('client_id=test_strava_client_id', strava_url)
        
        # Testar para Garmin
        garmin_url = self.manager.get_authorization_url('garmin')
        self.assertIn('oauth_consumer_key=test_garmin_consumer_key', garmin_url)
        
        # Testar para plataforma não suportada
        with self.assertRaises(ValueError):
            self.manager.get_authorization_url('unsupported_platform')
    
    @patch('strava_integration.StravaIntegration.exchange_code_for_token')
    def test_handle_authorization_callback_strava(self, mock_exchange):
        """Testa o processamento de callback de autorização do Strava"""
        # Configurar mock
        mock_exchange.return_value = {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'expires_at': 1619395200
        }
        
        # Chamar método
        result = self.manager.handle_authorization_callback(
            'strava',
            {'code': 'test_code'}
        )
        
        # Verificar resultado
        self.assertEqual(result['access_token'], 'test_access_token')
        self.assertEqual(result['refresh_token'], 'test_refresh_token')
    
    @patch('garmin_integration.GarminIntegration.exchange_token')
    def test_handle_authorization_callback_garmin(self, mock_exchange):
        """Testa o processamento de callback de autorização do Garmin"""
        # Configurar mock
        mock_exchange.return_value = {
            'oauth_token': 'test_oauth_token',
            'oauth_token_secret': 'test_token_secret',
            'user_id': '12345'
        }
        
        # Chamar método
        result = self.manager.handle_authorization_callback(
            'garmin',
            {'oauth_token': 'test_token', 'oauth_verifier': 'test_verifier'}
        )
        
        # Verificar resultado
        self.assertEqual(result['oauth_token'], 'test_oauth_token')
        self.assertEqual(result['oauth_token_secret'], 'test_token_secret')


if __name__ == '__main__':
    unittest.main()
