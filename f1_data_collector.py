import os
import requests
from pymongo import MongoClient, errors
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações Globais
BASE_URL = "https://api.openf1.org/v1"
DB_NAME = "openf1_data"

def get_db_connection() -> Database:
    """
    Lê a URI de conexão do MongoDB (.env), estabelece a conexão 
    e retorna a instância do banco de dados openf1_data.
    """
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    
    try:
        # Define um timeout para evitar que o script trave se o banco estiver offline
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # Testa a conexão ativamente
        print("Conexão com MongoDB estabelecida com sucesso.")
        return client[DB_NAME]
    except errors.ServerSelectionTimeoutError as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        raise

def fetch_data(endpoint: str, params: dict) -> list:
    """
    Faz uma requisição GET na API da OpenF1 e retorna a lista de resultados.
    """
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() # Dispara exceção para códigos de erro HTTP (4xx, 5xx)
        
        data = response.json()
        print(f"[{endpoint}] {len(data)} registros retornados da API.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição ao endpoint {endpoint}: {e}")
        return []

def save_to_collection(db: Database, data: list, collection_name: str, unique_keys: list):
    """
    Armazena os dados no MongoDB de forma idempotente, utilizando a instrução update_one 
    com upsert=True e baseando-se nas chaves únicas fornecidas.
    """
    if not data:
        print(f"[{collection_name}] Nenhum dado para salvar.")
        return

    collection: Collection = db[collection_name]
    inserted_count = 0
    updated_count = 0

    for item in data:
        # Monta um dicionário com os campos que formam a chave composta única
        filter_query = {key: item.get(key) for key in unique_keys if key in item}

        # upsert=True: Insere se não existir, atualiza se já existir
        result = collection.update_one(
            filter_query,
            {"$set": item},
            upsert=True
        )

        if result.upserted_id:
            inserted_count += 1
        else:
            updated_count += 1

    print(f"[{collection_name}] Operação finalizada -> Inseridos: {inserted_count} | Atualizados: {updated_count}.")

def main():
    """
    Execução principal do script que orquestra a coleta e armazenamento dos dados.
    """
    print("--- Iniciando Coletor de Dados OpenF1 ---")
    
    # 1. Conexão com o banco
    try:
        db = get_db_connection()
    except Exception:
        print("Execução abortada devido a erro no banco de dados.")
        return

    # Caso de uso de demonstração (GP da Itália 2023)
    session_key = 9159
    meeting_key = 1219

    # 2. Sessões
    print("\n[1/3] Coletando dados das sessões...")
    sessions_data = fetch_data("/sessions", {"session_key": session_key, "meeting_key": meeting_key})
    save_to_collection(db, sessions_data, "sessions", ["session_key"])

    # 3. Pilotos da sessão
    print("\n[2/3] Coletando dados dos pilotos...")
    drivers_data = fetch_data("/drivers", {"session_key": session_key})
    save_to_collection(db, drivers_data, "drivers", ["session_key", "driver_number"])

    # 4. Voltas da sessão
    print("\n[3/3] Coletando dados das voltas...")
    laps_data = fetch_data("/laps", {"session_key": session_key})
    save_to_collection(db, laps_data, "laps", ["session_key", "driver_number", "lap_number"])

    print("\n--- Ingestão concluída com sucesso! ---")

if __name__ == "__main__":
    main()