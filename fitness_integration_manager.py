"""
Módulo de integração com APIs de fitness para o Golden Runners
"""
import os
from datetime import datetime, timedelta
from strava_integration import StravaIntegration
from garmin_integration import GarminIntegration

class FitnessIntegrationManager:
    """
    Classe para gerenciar todas as integrações com apps de fitness
    """
    
    def __init__(self, config):
        """
        Inicializa o gerenciador de integrações
        
        Args:
            config (dict): Configurações para as diferentes integrações
        """
        self.config = config
        self.integrations = {}
        
        # Inicializar integração com Strava se configurado
        if 'strava' in config:
            self.integrations['strava'] = StravaIntegration(
                config['strava']['client_id'],
                config['strava']['client_secret'],
                config['strava']['redirect_uri']
            )
        
        # Inicializar integração com Garmin se configurado
        if 'garmin' in config:
            self.integrations['garmin'] = GarminIntegration(
                config['garmin']['consumer_key'],
                config['garmin']['consumer_secret'],
                config['garmin']['redirect_uri']
            )
    
    def get_authorization_url(self, platform):
        """
        Obtém URL de autorização para uma plataforma específica
        
        Args:
            platform (str): Nome da plataforma ('strava', 'garmin', etc.)
            
        Returns:
            str: URL de autorização
        """
        if platform not in self.integrations:
            raise ValueError(f"Plataforma não suportada: {platform}")
            
        return self.integrations[platform].get_authorization_url()
    
    def handle_authorization_callback(self, platform, params):
        """
        Processa callback de autorização de uma plataforma
        
        Args:
            platform (str): Nome da plataforma
            params (dict): Parâmetros do callback
            
        Returns:
            dict: Tokens de acesso e informações do usuário
        """
        if platform not in self.integrations:
            raise ValueError(f"Plataforma não suportada: {platform}")
        
        if platform == 'strava':
            code = params.get('code')
            if not code:
                raise ValueError("Código de autorização não encontrado")
                
            return self.integrations[platform].exchange_code_for_token(code)
            
        elif platform == 'garmin':
            oauth_token = params.get('oauth_token')
            oauth_verifier = params.get('oauth_verifier')
            if not oauth_token or not oauth_verifier:
                raise ValueError("Parâmetros OAuth não encontrados")
                
            return self.integrations[platform].exchange_token(oauth_token, oauth_verifier)
    
    def get_user_activities(self, platform, tokens, since=None, limit=30):
        """
        Obtém atividades do usuário de uma plataforma específica
        
        Args:
            platform (str): Nome da plataforma
            tokens (dict): Tokens de acesso
            since (datetime, optional): Data a partir da qual buscar atividades
            limit (int, optional): Número máximo de atividades
            
        Returns:
            list: Lista de atividades processadas para doação
        """
        if platform not in self.integrations:
            raise ValueError(f"Plataforma não suportada: {platform}")
            
        # Obter atividades da plataforma específica
        if platform == 'strava':
            access_token = tokens['access_token']
            activities = self.integrations[platform].get_activities(
                access_token, 
                after=since,
                per_page=limit
            )
            
        elif platform == 'garmin':
            access_token = tokens['oauth_token']
            token_secret = tokens['oauth_token_secret']
            activities = self.integrations[platform].get_activities(
                access_token,
                token_secret,
                limit=limit
            )
        
        # Processar atividades para doação
        processed_activities = []
        for activity in activities:
            if platform == 'strava':
                processed = self.integrations[platform].process_activity_for_donation(
                    activity,
                    donation_rate_per_km=self.config['donation_rates']['km'],
                    donation_rate_per_calorie=self.config['donation_rates']['calorie']
                )
            elif platform == 'garmin':
                processed = self.integrations[platform].process_activity_for_donation(
                    activity,
                    donation_rate_per_km=self.config['donation_rates']['km'],
                    donation_rate_per_calorie=self.config['donation_rates']['calorie']
                )
                
            processed['platform'] = platform
            processed_activities.append(processed)
            
        return processed_activities
    
    def refresh_tokens_if_needed(self, platform, tokens):
        """
        Atualiza tokens se necessário
        
        Args:
            platform (str): Nome da plataforma
            tokens (dict): Tokens atuais
            
        Returns:
            dict: Tokens atualizados ou os mesmos tokens se não precisar atualizar
        """
        if platform not in self.integrations:
            raise ValueError(f"Plataforma não suportada: {platform}")
            
        if platform == 'strava':
            # Verificar se o token expirou
            expires_at = tokens.get('expires_at', 0)
            now = datetime.now().timestamp()
            
            if now >= expires_at:
                # Token expirou, atualizar
                refresh_token = tokens.get('refresh_token')
                if not refresh_token:
                    raise ValueError("Refresh token não encontrado")
                    
                return self.integrations[platform].refresh_token(refresh_token)
                
        # Para Garmin, os tokens não expiram da mesma forma que o Strava
        return tokens


# Exemplo de uso
if __name__ == "__main__":
    # Configuração de exemplo
    config = {
        'strava': {
            'client_id': 'YOUR_STRAVA_CLIENT_ID',
            'client_secret': 'YOUR_STRAVA_CLIENT_SECRET',
            'redirect_uri': 'https://goldenrunners.example.com/strava/callback'
        },
        'garmin': {
            'consumer_key': 'YOUR_GARMIN_CONSUMER_KEY',
            'consumer_secret': 'YOUR_GARMIN_CONSUMER_SECRET',
            'redirect_uri': 'https://goldenrunners.example.com/garmin/callback'
        },
        'donation_rates': {
            'km': 2.0,  # R$ 2,00 por km
            'calorie': 0.01  # R$ 0,01 por caloria
        }
    }
    
    # Inicializar gerenciador
    manager = FitnessIntegrationManager(config)
    
    # Obter URLs de autorização
    strava_auth_url = manager.get_authorization_url('strava')
    garmin_auth_url = manager.get_authorization_url('garmin')
    
    print(f"URL de autorização Strava: {strava_auth_url}")
    print(f"URL de autorização Garmin: {garmin_auth_url}")
    
    # Simular processamento de callback do Strava
    strava_callback_params = {'code': 'SIMULATED_CODE'}
    strava_tokens = manager.handle_authorization_callback('strava', strava_callback_params)
    
    # Simular obtenção de atividades do Strava
    since_date = datetime.now() - timedelta(days=30)  # Últimos 30 dias
    strava_activities = manager.get_user_activities('strava', strava_tokens, since=since_date)
    
    print(f"Encontradas {len(strava_activities)} atividades no Strava")
    for activity in strava_activities:
        print(f"Atividade: {activity['activity_type']}")
        print(f"Distância: {activity['distance_km']} km")
        print(f"Doação: R$ {activity['donation_amount']}")
        print("---")
