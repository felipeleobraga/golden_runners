"""
Módulo de integração com a API do Strava para o Golden Runners
"""
import os
import requests
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

class StravaIntegration:
    """
    Classe para gerenciar a integração com a API do Strava
    """
    
    BASE_URL = "https://www.strava.com/api/v3"
    AUTH_URL = "https://www.strava.com/oauth/authorize"
    TOKEN_URL = "https://www.strava.com/oauth/token"
    
    def __init__(self, client_id, client_secret, redirect_uri):
        """
        Inicializa a integração com o Strava
        
        Args:
            client_id (str): ID do cliente Strava
            client_secret (str): Secret do cliente Strava
            redirect_uri (str): URI de redirecionamento após autenticação
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        
    def get_authorization_url(self, scope="read,activity:read_all"):
        """
        Gera a URL para autorização do usuário
        
        Args:
            scope (str): Escopos de permissão solicitados
            
        Returns:
            str: URL de autorização
        """
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'approval_prompt': 'force',
            'scope': scope
        }
        
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code):
        """
        Troca o código de autorização por tokens de acesso
        
        Args:
            code (str): Código de autorização
            
        Returns:
            dict: Tokens de acesso e informações do atleta
        """
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        if response.status_code != 200:
            raise Exception(f"Erro ao obter token: {response.text}")
            
        return response.json()
    
    def refresh_token(self, refresh_token):
        """
        Atualiza o token de acesso usando o refresh token
        
        Args:
            refresh_token (str): Token de atualização
            
        Returns:
            dict: Novos tokens de acesso
        """
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        if response.status_code != 200:
            raise Exception(f"Erro ao atualizar token: {response.text}")
            
        return response.json()
    
    def get_athlete_info(self, access_token):
        """
        Obtém informações do atleta
        
        Args:
            access_token (str): Token de acesso
            
        Returns:
            dict: Informações do atleta
        """
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(f"{self.BASE_URL}/athlete", headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Erro ao obter informações do atleta: {response.text}")
            
        return response.json()
    
    def get_activities(self, access_token, after=None, page=1, per_page=30):
        """
        Obtém atividades do atleta
        
        Args:
            access_token (str): Token de acesso
            after (datetime, optional): Data a partir da qual buscar atividades
            page (int, optional): Página de resultados
            per_page (int, optional): Número de resultados por página
            
        Returns:
            list: Lista de atividades
        """
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {
            'page': page,
            'per_page': per_page
        }
        
        if after:
            params['after'] = int(after.timestamp())
        
        response = requests.get(
            f"{self.BASE_URL}/athlete/activities", 
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            raise Exception(f"Erro ao obter atividades: {response.text}")
            
        return response.json()
    
    def get_activity_details(self, access_token, activity_id):
        """
        Obtém detalhes de uma atividade específica
        
        Args:
            access_token (str): Token de acesso
            activity_id (str): ID da atividade
            
        Returns:
            dict: Detalhes da atividade
        """
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(
            f"{self.BASE_URL}/activities/{activity_id}", 
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Erro ao obter detalhes da atividade: {response.text}")
            
        return response.json()
    
    def process_activity_for_donation(self, activity, donation_rate_per_km=2.0, donation_rate_per_calorie=0.01):
        """
        Processa uma atividade para calcular o valor da doação
        
        Args:
            activity (dict): Dados da atividade
            donation_rate_per_km (float): Valor de doação por km
            donation_rate_per_calorie (float): Valor de doação por caloria
            
        Returns:
            dict: Informações processadas da atividade com valor de doação
        """
        # Extrair dados relevantes da atividade
        activity_id = activity.get('id')
        activity_type = activity.get('type')
        distance_meters = activity.get('distance', 0)
        distance_km = distance_meters / 1000
        calories = activity.get('calories', 0)
        start_date = activity.get('start_date')
        
        # Calcular doação
        donation_from_distance = distance_km * donation_rate_per_km
        donation_from_calories = calories * donation_rate_per_calorie
        total_donation = donation_from_distance + donation_from_calories
        
        return {
            'activity_id': activity_id,
            'activity_type': activity_type,
            'distance_km': round(distance_km, 2),
            'calories': calories,
            'start_date': start_date,
            'donation_amount': round(total_donation, 2)
        }
    
    def subscribe_to_webhook(self, callback_url, verify_token):
        """
        Inscreve-se para receber webhooks do Strava
        
        Args:
            callback_url (str): URL para receber callbacks
            verify_token (str): Token de verificação
            
        Returns:
            dict: Resposta da inscrição
        """
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'callback_url': callback_url,
            'verify_token': verify_token
        }
        
        response = requests.post(
            "https://www.strava.com/api/v3/push_subscriptions",
            data=data
        )
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Erro ao inscrever-se para webhooks: {response.text}")
            
        return response.json()


# Exemplo de uso
if __name__ == "__main__":
    # Estas credenciais seriam armazenadas em variáveis de ambiente em produção
    CLIENT_ID = "YOUR_CLIENT_ID"
    CLIENT_SECRET = "YOUR_CLIENT_SECRET"
    REDIRECT_URI = "https://goldenrunners.example.com/strava/callback"
    
    strava = StravaIntegration(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    
    # Gerar URL de autorização
    auth_url = strava.get_authorization_url()
    print(f"URL de autorização: {auth_url}")
    
    # Após o usuário autorizar, você receberá um código
    # Troque o código por tokens
    code = "AUTHORIZATION_CODE"  # Este código viria do callback
    tokens = strava.exchange_code_for_token(code)
    
    # Armazenar tokens (em um banco de dados em produção)
    access_token = tokens['access_token']
    refresh_token = tokens['refresh_token']
    expires_at = tokens['expires_at']
    
    # Obter informações do atleta
    athlete = strava.get_athlete_info(access_token)
    print(f"Atleta: {athlete['firstname']} {athlete['lastname']}")
    
    # Obter atividades recentes
    activities = strava.get_activities(access_token)
    
    # Processar atividades para doação
    for activity in activities:
        donation_info = strava.process_activity_for_donation(activity)
        print(f"Atividade: {donation_info['activity_type']}")
        print(f"Distância: {donation_info['distance_km']} km")
        print(f"Calorias: {donation_info['calories']}")
        print(f"Doação: R$ {donation_info['donation_amount']}")
        print("---")
