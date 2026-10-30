"""Autenticação e perfis de usuário (senha com hash PBKDF2 + salt).

As senhas nunca são guardadas em texto puro: o banco (coleção `usuarios`)
guarda apenas o salt e o hash gerado com PBKDF2-HMAC-SHA256.

Tentativas inválidas são contadas no banco (coleção `tentativas_login`), então
o bloqueio continua valendo mesmo que o programa seja fechado e reaberto.
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

ITERACOES = 600_000          # recomendação atual para PBKDF2-HMAC-SHA256
ITERACOES_ANTIGAS = 200_000  # contas criadas antes de existir o campo "iteracoes"
SENHA_MINIMA = 8
MAX_FALHAS = 5               # por usuário (e, na API, por usuário + origem)
MAX_FALHAS_POR_ORIGEM = 30   # por endereço de origem, para qualquer usuário (barra o chute em massa)
BLOQUEIO_MINUTOS = 5

# Perfis: um único administrador (o 1º acesso) + até MAX_USUARIOS_EXTRAS usuários de outros perfis.
PERFIL_ADMIN = "administrador"
PERFIL_PROFESSOR = "professor"   # só lança/edita notas e faz consultas (boletim, ranking, risco)
PERFIL_CONSULTA = "consulta"     # só visualiza
PERFIS_EXTRAS = (PERFIL_PROFESSOR, PERFIL_CONSULTA)
MAX_USUARIOS_EXTRAS = 3


class LimiteUsuariosError(Exception):
    """Já existem MAX_USUARIOS_EXTRAS usuários além do administrador."""


class BloqueadoError(Exception):
    """Usuário bloqueado por excesso de tentativas; `segundos` diz quanto falta."""

    def __init__(self, segundos):
        super().__init__(f"Bloqueado por mais {segundos} segundos.")
        self.segundos = segundos


def _agora():
    return datetime.now(timezone.utc)


def _como_utc(data):
    # O pymongo devolve datas sem fuso (já em UTC) por padrão.
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def gerar_hash(senha, salt=None, iteracoes=None):
    """Devolve (salt_hex, hash_hex) da senha. Gera um salt novo se não for informado."""
    salt = salt or os.urandom(16)
    resultado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes or ITERACOES)
    return salt.hex(), resultado.hex()


def verificar_senha(senha, salt_hex, hash_hex, iteracoes=None):
    """Confere a senha digitada contra o hash guardado (comparação em tempo constante)."""
    _, calculado = gerar_hash(senha, bytes.fromhex(salt_hex), iteracoes or ITERACOES_ANTIGAS)
    return hmac.compare_digest(calculado, hash_hex)


def validar_senha(senha):
    """Devolve uma mensagem de erro se a senha for fraca, ou None se estiver ok."""
    if len(senha) < SENHA_MINIMA:
        return f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres."
    if not any(c.isalpha() for c in senha) or not any(c.isdigit() for c in senha):
        return "A senha deve misturar letras e números."
    return None


def codigo_configuracao_exigido():
    """True se ADMIN_SETUP_CODE está definido (exigido ao criar o 1º administrador)."""
    return bool(os.getenv("ADMIN_SETUP_CODE"))


def codigo_configuracao_confere(digitado):
    esperado = os.getenv("ADMIN_SETUP_CODE")
    if not esperado:
        return True
    return hmac.compare_digest(digitado.encode("utf-8"), esperado.encode("utf-8"))


def existe_admin(banco):
    """Indica se já existe algum administrador cadastrado."""
    return banco.usuarios.count_documents({}, limit=1) > 0


def criar_admin(banco, usuario, senha):
    """Cadastra um administrador. Lança DuplicateKeyError se o usuário já existir."""
    erro = validar_senha(senha)
    if erro:
        raise ValueError(erro)
    salt, hash_senha = gerar_hash(senha)
    documento = {
        "usuario": usuario.strip().lower(),
        "perfil": PERFIL_ADMIN,
        "salt": salt,
        "hash": hash_senha,
        "iteracoes": ITERACOES,
        "data_cadastro": _agora(),
    }
    banco.usuarios.insert_one(documento)
    return documento


def criar_primeiro_admin(banco, usuario, senha):
    """Como criar_admin, mas só funciona enquanto não existe nenhum administrador."""
    if existe_admin(banco):
        raise PermissionError("Já existe um administrador cadastrado.")
    return criar_admin(banco, usuario, senha)


def perfil_do(documento):
    """Perfil do usuário. Contas antigas, sem o campo, são administradoras."""
    return documento.get("perfil", PERFIL_ADMIN)


def contar_extras(banco):
    """Quantos usuários existem além do administrador."""
    return banco.usuarios.count_documents({"perfil": {"$in": list(PERFIS_EXTRAS)}})


def listar_usuarios(banco):
    """Todos os usuários (sem salt/hash), administrador primeiro."""
    usuarios = list(banco.usuarios.find({}, {"salt": 0, "hash": 0}))
    return sorted(usuarios, key=lambda u: (perfil_do(u) != PERFIL_ADMIN, u["usuario"]))


def criar_usuario(banco, usuario, senha, perfil):
    """Cadastra um usuário professor ou consulta. Só o administrador deve chamar isto.

    Lança LimiteUsuariosError no 4º usuário extra, DuplicateKeyError se o nome já existir
    e ValueError para perfil, nome ou senha inválidos."""
    if perfil not in PERFIS_EXTRAS:
        raise ValueError(f"Perfil inválido. Use: {', '.join(PERFIS_EXTRAS)}.")
    nome = usuario.strip().lower()
    if not nome:
        raise ValueError("Informe o nome do usuário.")
    erro = validar_senha(senha)
    if erro:
        raise ValueError(erro)
    if contar_extras(banco) >= MAX_USUARIOS_EXTRAS:
        raise LimiteUsuariosError(
            f"Limite atingido: no máximo {MAX_USUARIOS_EXTRAS} usuários além do administrador.")
    salt, hash_senha = gerar_hash(senha)
    documento = {"usuario": nome, "perfil": perfil, "salt": salt, "hash": hash_senha,
                 "iteracoes": ITERACOES, "data_cadastro": _agora()}
    banco.usuarios.insert_one(documento)
    return documento


def trocar_senha(banco, usuario, nova_senha):
    """Define uma senha nova (e libera o usuário de um bloqueio). False se o usuário não existe."""
    erro = validar_senha(nova_senha)
    if erro:
        raise ValueError(erro)
    nome = usuario.strip().lower()
    salt, hash_senha = gerar_hash(nova_senha)
    resultado = banco.usuarios.update_one(
        {"usuario": nome},
        {"$set": {"salt": salt, "hash": hash_senha, "iteracoes": ITERACOES,
                  "senha_alterada_em": _agora()}})
    _limpar_falhas(banco, nome)
    return resultado.matched_count > 0


def sessao_vale(documento, emitido_em):
    """False se a senha foi trocada depois de o token ser emitido (`emitido_em` em segundos)."""
    alterada = documento.get("senha_alterada_em")
    return not alterada or emitido_em >= int(_como_utc(alterada).timestamp())


def excluir_usuario(banco, usuario):
    """Exclui um usuário. O administrador nunca pode ser excluído (PermissionError)."""
    nome = usuario.strip().lower()
    documento = banco.usuarios.find_one({"usuario": nome})
    if not documento:
        return False
    if perfil_do(documento) == PERFIL_ADMIN:
        raise PermissionError("O administrador não pode ser excluído.")
    banco.usuarios.delete_one({"_id": documento["_id"]})
    _limpar_falhas(banco, nome)
    return True


def _limpar_falhas(banco, usuario):
    """Apaga os contadores do usuário, de qualquer origem."""
    banco.tentativas_login.delete_many({"$or": [{"_id": usuario}, {"usuario": usuario}]})


def segundos_de_bloqueio(banco, chave):
    """Segundos que faltam para a chave (usuário ou origem) poder tentar de novo (0 = liberado)."""
    registro = banco.tentativas_login.find_one({"_id": chave})
    if not registro or not registro.get("bloqueado_ate"):
        return 0
    restante = (_como_utc(registro["bloqueado_ate"]) - _agora()).total_seconds()
    return int(restante) + 1 if restante > 0 else 0


def registrar_falha(banco, chave, usuario=None, limite=MAX_FALHAS):
    """Conta uma tentativa inválida na chave e a bloqueia ao atingir o limite."""
    campos = {"atualizado_em": _agora()}
    if usuario:
        campos["usuario"] = usuario
    registro = banco.tentativas_login.find_one_and_update(
        {"_id": chave},
        {"$inc": {"falhas": 1}, "$set": campos},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if registro["falhas"] >= limite:
        banco.tentativas_login.update_one(
            {"_id": chave},
            {"$set": {"falhas": 0,
                      "bloqueado_ate": _agora() + timedelta(minutes=BLOQUEIO_MINUTOS)}},
        )


def autenticar(banco, usuario, senha, origem=None):
    """Devolve o documento do usuário se as credenciais estiverem corretas, senão None.

    `origem` (na API, o endereço de quem chama) separa os contadores: quem erra a senha de
    "admin" de um endereço só bloqueia esse endereço, não o administrador de verdade. Além disso
    cada origem tem um limite geral (MAX_FALHAS_POR_ORIGEM), que também impede encher o banco com
    usuários inventados. Sem `origem` (tela e terminal, uso local) vale só o limite por usuário.

    Lança BloqueadoError se o usuário (ou a origem) estiver bloqueado por tentativas inválidas.
    Contas antigas, com menos iterações no hash, são regravadas com o hash atual no login.
    """
    usuario = usuario.strip().lower()
    chave_usuario = f"{usuario}|{origem}" if origem else usuario
    chave_origem = f"ip|{origem}" if origem else None
    for chave in (chave_usuario, chave_origem):
        restante = segundos_de_bloqueio(banco, chave) if chave else 0
        if restante:
            raise BloqueadoError(restante)

    documento = banco.usuarios.find_one({"usuario": usuario})
    if not documento:
        gerar_hash(senha)  # gasta o mesmo tempo, para não revelar se o usuário existe
    else:
        iteracoes = documento.get("iteracoes", ITERACOES_ANTIGAS)
        if verificar_senha(senha, documento["salt"], documento["hash"], iteracoes):
            banco.tentativas_login.delete_one({"_id": chave_usuario})
            if iteracoes < ITERACOES:
                salt, novo = gerar_hash(senha)
                banco.usuarios.update_one({"_id": documento["_id"]},
                                          {"$set": {"salt": salt, "hash": novo, "iteracoes": ITERACOES}})
            return documento
    registrar_falha(banco, chave_usuario, usuario)
    if chave_origem:
        registrar_falha(banco, chave_origem, limite=MAX_FALHAS_POR_ORIGEM)
    return None
