import os
import sys
import psycopg2
from urllib.parse import urlparse

# Tabelas a serem criadas
CREATE_TABLES_SQL = [
    """
    DROP TABLE IF EXISTS users CASCADE;
    """,
    """
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(128) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    # Outras tabelas aqui...
]

def initialize_database():
    print("=== INICIANDO SCRIPT DE INICIALIZAÇÃO DO BANCO DE DADOS ===")
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: Variável de ambiente DATABASE_URL não definida.")
        sys.exit(1)
    
    print(f"Conectando ao banco de dados com URL: {db_url[:20]}...")
    
    conn = None
    try:
        # Conectar ao banco de dados PostgreSQL
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("Conectado ao banco de dados com sucesso!")
        print("Iniciando criação/recriação de tabelas...")
        
        # Executar comandos SQL
        for i, sql_command in enumerate(CREATE_TABLES_SQL):
            print(f"Executando comando SQL #{i+1}...")
            cur.execute(sql_command)
            print(f"Comando SQL #{i+1} executado com sucesso!")
        
        # Commit das alterações
        conn.commit()
        print("Todas as tabelas foram criadas/recriadas com sucesso!")
        
        # Fechar comunicação
        cur.close()
    except Exception as e:
        print(f"ERRO CRÍTICO ao conectar ou inicializar o banco de dados: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn is not None:
            conn.close()
            print("Conexão com o banco de dados fechada.")
    
    print("=== SCRIPT DE INICIALIZAÇÃO CONCLUÍDO COM SUCESSO ===")

if __name__ == "__main__":
    initialize_database()
