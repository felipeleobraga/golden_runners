import os
import psycopg2
from urllib.parse import urlparse

# Tabelas a serem criadas (adicione mais conforme necessário)
CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        -- Adicione colunas para tokens de API (Strava, Garmin) criptografados
        -- strava_access_token TEXT,
        -- strava_refresh_token TEXT,
        -- strava_expires_at INTEGER,
        -- garmin_token TEXT,
        -- garmin_token_secret TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS activities (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) NOT NULL,
        platform VARCHAR(50) NOT NULL, -- 'strava', 'garmin', 'manual'
        platform_activity_id VARCHAR(100), -- ID da atividade na plataforma original
        type VARCHAR(50), -- 'Run', 'Ride', etc.
        start_time TIMESTAMP NOT NULL,
        distance_km REAL,
        duration_seconds INTEGER,
        calories REAL,
        donation_amount REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS donation_items (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) NOT NULL,
        title VARCHAR(200) NOT NULL,
        description TEXT,
        category VARCHAR(100),
        location VARCHAR(200),
        image_url TEXT,
        status VARCHAR(50) DEFAULT 'available', -- 'available', 'reserved', 'donated'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS interests (
        id SERIAL PRIMARY KEY,
        item_id INTEGER REFERENCES donation_items(id) NOT NULL,
        interested_user_id INTEGER REFERENCES users(id) NOT NULL,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(item_id, interested_user_id) -- Evita interesse duplicado
    );
    """
    # Adicione aqui CREATE TABLE para patrocinadores, instituições, etc., se necessário
]

def initialize_database():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Erro: Variável de ambiente DATABASE_URL não definida.")
        return

    conn = None
    try:
        # Conectar ao banco de dados PostgreSQL
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        print("Conectado ao banco de dados. Criando tabelas...")

        # Executar comandos CREATE TABLE
        for sql_command in CREATE_TABLES_SQL:
            cur.execute(sql_command)
            print(f"Executado: {sql_command[:60]}...") # Log curto do comando

        # Commit das alterações
        conn.commit()
        print("Tabelas criadas com sucesso (ou já existiam).")

        # Fechar comunicação
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Erro ao conectar ou inicializar o banco de dados: {error}")
    finally:
        if conn is not None:
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    print("Iniciando script de inicialização do banco de dados...")
    initialize_database()
    print("Script de inicialização concluído.")

