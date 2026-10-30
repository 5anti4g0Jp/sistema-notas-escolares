"""Conexão com o MongoDB Atlas e criação de índices."""

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

from config import NOME_BANCO, obter_uri_mongodb

UM_DIA = 24 * 60 * 60


def conectar_banco():
    """Conecta ao MongoDB Atlas, testa a conexão e prepara os índices."""
    uri = obter_uri_mongodb()
    cliente = MongoClient(uri, serverSelectionTimeoutMS=5000)
    cliente.admin.command("ping")
    banco = cliente[NOME_BANCO]
    criar_indices(banco)
    return cliente, banco


def criar_indices(banco):
    """Cria os índices únicos que garantem a integridade dos dados."""
    banco.alunos.create_index("matricula", unique=True)
    banco.disciplinas.create_index("codigo", unique=True)
    banco.usuarios.create_index("usuario", unique=True)
    # Registros de login falho somem sozinhos 1 dia após a última tentativa.
    banco.tentativas_login.create_index("atualizado_em", expireAfterSeconds=UM_DIA)
    banco.notas.create_index("aluno_id")
    banco.notas.create_index("disciplina_id")
    # O índice antigo usava "bimestre"; agora o sistema trabalha com semestres.
    try:
        banco.notas.drop_index("aluno_id_1_disciplina_id_1_bimestre_1")
    except OperationFailure:
        pass  # já foi removido (ou nunca existiu)
    banco.notas.create_index(
        [("aluno_id", ASCENDING), ("disciplina_id", ASCENDING), ("semestre", ASCENDING)],
        unique=True,
        partialFilterExpression={"semestre": {"$exists": True}},
    )
