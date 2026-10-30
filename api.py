"""API REST do sistema de notas escolares (FastAPI).

Reaproveita as mesmas regras (calculos.py, risco.py) e os mesmos perfis da tela:
administrador (tudo), professor (vê tudo e lança notas) e consulta (só visualiza).

Executar (precisa de MONGODB_URI):   python api.py
Sem banco real, com dados de exemplo: python api.py --demo      (precisa de mongomock)
Documentação interativa:              http://127.0.0.1:8000/docs

Variáveis de ambiente: MONGODB_URI, API_SECRET (assina os tokens; se faltar, um segredo
aleatório é criado a cada execução e os tokens deixam de valer ao reiniciar),
API_TOKEN_HORAS (validade do token, padrão 8), ADMIN_SETUP_CODE (opcional, 1º acesso).
"""

import os
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import autenticacao
import professores
from calculos import (SEMESTRES, media_da_nota, montar_boletim, notas_do_aluno, ranking_turmas)
from risco import avaliar_aluno, avaliar_todos

ADMIN = autenticacao.PERFIL_ADMIN
PROFESSOR = autenticacao.PERFIL_PROFESSOR
CONSULTA = autenticacao.PERFIL_CONSULTA
TODOS = (ADMIN, PROFESSOR, CONSULTA)


# ---------- modelos de entrada ----------
class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=200)


class PrimeiroAcessoIn(LoginIn):
    codigo_configuracao: Optional[str] = None


class AlunoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    matricula: str = Field(min_length=1, max_length=40)
    turma: str = Field(min_length=1, max_length=40)


class DisciplinaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    codigo: str = Field(min_length=1, max_length=40)
    carga_horaria: int = Field(ge=1, le=10000)


class NotasIn(BaseModel):
    """Provas de 0 a 10; omitir ou null = não lançada. Pelo menos uma é obrigatória."""
    avg: Optional[float] = Field(default=None, ge=0, le=10)
    avi: Optional[float] = Field(default=None, ge=0, le=10)
    avc: Optional[float] = Field(default=None, ge=0, le=10)


class UsuarioIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=200)
    perfil: str


class SenhaIn(BaseModel):
    senha: str = Field(min_length=1, max_length=200)


# ---------- utilidades ----------
def _oid(texto):
    try:
        return ObjectId(texto)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado.")


def _aluno_json(a):
    return {"id": str(a["_id"]), "nome": a["nome"], "matricula": a["matricula"], "turma": a["turma"]}


def _disciplina_json(d):
    return {"id": str(d["_id"]), "nome": d["nome"], "codigo": d["codigo"], "carga_horaria": d["carga_horaria"]}


def _nota_json(d):
    return {"disciplina": d["disciplina"], "semestre": d["semestre"], "avg": d.get("avg"),
            "avi": d.get("avi"), "avc": d.get("avc"), "media": media_da_nota(d)}


def _arredondar(valor):
    return None if valor is None else round(valor, 2)


def criar_token(usuario, segredo, horas):
    agora = datetime.now(timezone.utc)
    return jwt.encode({"sub": usuario, "iat": agora, "exp": agora + timedelta(hours=horas)},
                      segredo, algorithm="HS256")


def criar_app(banco=None):
    """Cria a aplicação. Sem `banco`, conecta ao MongoDB (MONGODB_URI) ao iniciar."""
    segredo = os.getenv("API_SECRET") or secrets.token_hex(32)
    horas = float(os.getenv("API_TOKEN_HORAS", "8"))
    segredo_aleatorio = not os.getenv("API_SECRET")
    cliente_mongo = []

    @asynccontextmanager
    async def ciclo_de_vida(app):
        if banco is None:
            from banco import conectar_banco
            cliente, app.state.banco = conectar_banco()
            cliente_mongo.append(cliente)
        else:
            app.state.banco = banco
        if segredo_aleatorio:
            print("Aviso: API_SECRET não definido; usando um segredo aleatório (tokens somem ao reiniciar).")
        yield
        for cliente in cliente_mongo:
            cliente.close()

    app = FastAPI(title="Sistema de Notas Escolares - API", version="1.0",
                  description="API REST: alunos, disciplinas, notas, boletim, ranking, risco e usuários.",
                  lifespan=ciclo_de_vida)
    bearer = HTTPBearer(auto_error=False)

    def obter_banco(request: Request):
        return request.app.state.banco

    def usuario_atual(cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                      bd=Depends(obter_banco)):
        erro = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente, inválido ou expirado.",
                             headers={"WWW-Authenticate": "Bearer"})
        if cred is None:
            raise erro
        try:
            dados = jwt.decode(cred.credentials, segredo, algorithms=["HS256"])
            nome, emitido_em = dados["sub"], int(dados["iat"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise erro
        documento = bd.usuarios.find_one({"usuario": nome})  # usuário excluído perde o acesso na hora
        if not documento or not autenticacao.sessao_vale(documento, emitido_em):  # senha trocada: token morre
            raise erro
        return {"usuario": nome, "perfil": autenticacao.perfil_do(documento)}

    def exigir(*perfis):
        def verificar(atual=Depends(usuario_atual)):
            if atual["perfil"] not in perfis:
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                                    f"O perfil {atual['perfil']} não pode realizar esta ação.")
            return atual
        return verificar

    def aluno_ou_404(bd, aluno_id):
        aluno = bd.alunos.find_one({"_id": _oid(aluno_id)})
        if not aluno:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Aluno não encontrado.")
        return aluno

    # ---------- acesso ----------
    @app.get("/", tags=["Geral"])
    def raiz():
        return {"sistema": "Sistema de Notas Escolares", "docs": "/docs"}

    @app.post("/primeiro-acesso", status_code=201, tags=["Acesso"])
    def primeiro_acesso(dados: PrimeiroAcessoIn, bd=Depends(obter_banco)):
        """Cria o administrador. Só funciona enquanto não existir nenhum usuário."""
        if autenticacao.existe_admin(bd):
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um administrador cadastrado.")
        if autenticacao.codigo_configuracao_exigido() and not autenticacao.codigo_configuracao_confere(
                dados.codigo_configuracao or ""):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Código de configuração incorreto.")
        try:
            autenticacao.criar_primeiro_admin(bd, dados.usuario, dados.senha)
        except ValueError as erro:
            raise HTTPException(422, str(erro))
        except PermissionError as erro:
            raise HTTPException(status.HTTP_409_CONFLICT, str(erro))
        return {"usuario": dados.usuario.strip().lower(), "perfil": ADMIN}

    @app.post("/login", tags=["Acesso"])
    def login(dados: LoginIn, response: Response, bd=Depends(obter_banco)):
        """Devolve um token (Bearer). 5 senhas erradas seguidas bloqueiam o usuário por 5 minutos."""
        try:
            documento = autenticacao.autenticar(bd, dados.usuario, dados.senha)
        except autenticacao.BloqueadoError as erro:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                f"Muitas tentativas inválidas. Tente de novo em {-(-erro.segundos // 60)} min.",
                                headers={"Retry-After": str(erro.segundos)})
        if not documento:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha incorretos.")
        nome = documento["usuario"]
        return {"access_token": criar_token(nome, segredo, horas), "token_type": "bearer",
                "usuario": nome, "perfil": autenticacao.perfil_do(documento), "expira_em_horas": horas}

    @app.get("/me", tags=["Acesso"])
    def me(atual=Depends(usuario_atual)):
        return atual

    # ---------- alunos ----------
    @app.get("/alunos", tags=["Alunos"])
    def listar_alunos(turma: Optional[str] = None, busca: Optional[str] = Query(None, description="nome ou matrícula"),
                      bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        filtro = {"turma": turma} if turma else {}
        alunos = list(bd.alunos.find(filtro).sort([("turma", 1), ("nome", 1)]))
        if busca:
            alvo = busca.strip().casefold()
            alunos = [a for a in alunos if alvo in a["nome"].casefold() or alvo in a["matricula"].casefold()]
        return [_aluno_json(a) for a in alunos]

    @app.post("/alunos", status_code=201, tags=["Alunos"])
    def criar_aluno(dados: AlunoIn, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        try:
            novo = bd.alunos.insert_one({**dados.model_dump(), "data_cadastro": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Essa matrícula já está cadastrada.")
        return {"id": str(novo.inserted_id), **dados.model_dump()}

    @app.get("/alunos/{aluno_id}", tags=["Alunos"])
    def ver_aluno(aluno_id: str, bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        return _aluno_json(aluno_ou_404(bd, aluno_id))

    @app.put("/alunos/{aluno_id}", tags=["Alunos"])
    def alterar_aluno(aluno_id: str, dados: AlunoIn, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        aluno_ou_404(bd, aluno_id)
        try:
            bd.alunos.update_one({"_id": _oid(aluno_id)}, {"$set": dados.model_dump()})
        except DuplicateKeyError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Essa matrícula já está cadastrada.")
        return {"id": aluno_id, **dados.model_dump()}

    @app.delete("/alunos/{aluno_id}", status_code=204, tags=["Alunos"])
    def excluir_aluno(aluno_id: str, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        """Exclui o aluno e as notas dele."""
        aluno = aluno_ou_404(bd, aluno_id)
        bd.notas.delete_many({"aluno_id": aluno["_id"]})
        bd.alunos.delete_one({"_id": aluno["_id"]})
        return Response(status_code=204)

    # ---------- disciplinas ----------
    @app.get("/disciplinas", tags=["Disciplinas"])
    def listar_disciplinas(bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        return [_disciplina_json(d) for d in bd.disciplinas.find().sort("nome", 1)]

    @app.post("/disciplinas", status_code=201, tags=["Disciplinas"])
    def criar_disciplina(dados: DisciplinaIn, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        try:
            nova = bd.disciplinas.insert_one(dados.model_dump())
        except DuplicateKeyError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esse código já está cadastrado.")
        return {"id": str(nova.inserted_id), **dados.model_dump()}

    @app.put("/disciplinas/{disciplina_id}", tags=["Disciplinas"])
    def alterar_disciplina(disciplina_id: str, dados: DisciplinaIn, bd=Depends(obter_banco),
                           _=Depends(exigir(ADMIN))):
        try:
            resultado = bd.disciplinas.update_one({"_id": _oid(disciplina_id)}, {"$set": dados.model_dump()})
        except DuplicateKeyError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esse código já está cadastrado.")
        if not resultado.matched_count:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Disciplina não encontrada.")
        return {"id": disciplina_id, **dados.model_dump()}

    @app.delete("/disciplinas/{disciplina_id}", status_code=204, tags=["Disciplinas"])
    def excluir_disciplina(disciplina_id: str, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        """Exclui a disciplina e as notas lançadas nela."""
        oid = _oid(disciplina_id)
        if not bd.disciplinas.find_one({"_id": oid}):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Disciplina não encontrada.")
        bd.notas.delete_many({"disciplina_id": oid})
        professores.remover_disciplina_dos_professores(bd, oid)
        bd.disciplinas.delete_one({"_id": oid})
        return Response(status_code=204)

    # ---------- notas e consultas ----------
    @app.get("/alunos/{aluno_id}/notas", tags=["Notas"])
    def notas_do_aluno_api(aluno_id: str, bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        aluno = aluno_ou_404(bd, aluno_id)
        return [_nota_json(d) for d in notas_do_aluno(bd, aluno["_id"])]

    @app.put("/alunos/{aluno_id}/notas/{disciplina_id}/{semestre}", tags=["Notas"])
    def lancar_notas(aluno_id: str, disciplina_id: str, notas: NotasIn,
                     semestre: int = Path(ge=1, le=SEMESTRES),
                     professor_id: Optional[str] = Query(None, description="obrigatório se a turma tem mais de "
                                                         "um professor na disciplina"),
                     bd=Depends(obter_banco), _=Depends(exigir(ADMIN, PROFESSOR))):
        """Cria ou atualiza as notas (AVG, AVI, AVC) do aluno na disciplina e semestre.

        Se a turma do aluno tem alocações, só vale um professor alocado nela naquela disciplina."""
        aluno = aluno_ou_404(bd, aluno_id)
        disciplina = bd.disciplinas.find_one({"_id": _oid(disciplina_id)})
        if not disciplina:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Disciplina não encontrada.")
        provas = {"avg": notas.avg, "avi": notas.avi, "avc": notas.avc}
        if all(v is None for v in provas.values()):
            raise HTTPException(422, "Informe pelo menos uma nota.")
        provas = {k: _arredondar(v) for k, v in provas.items()}
        try:
            dono = professores.resolver_professor(
                bd, aluno["turma"], disciplina["_id"], _oid(professor_id) if professor_id else None)
        except professores.RegraError as erro:
            raise HTTPException(status.HTTP_409_CONFLICT, str(erro))
        filtro = {"aluno_id": aluno["_id"], "disciplina_id": disciplina["_id"], "semestre": semestre,
                  "professor_id": dono}
        bd.notas.replace_one(filtro, {**filtro, **provas, "data_lancamento": datetime.now(timezone.utc)},
                             upsert=True)
        return {"aluno": aluno["nome"], "disciplina": disciplina["nome"], "semestre": semestre,
                **provas, "media": media_da_nota(provas)}

    @app.get("/alunos/{aluno_id}/boletim", tags=["Consultas"])
    def boletim(aluno_id: str, bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        aluno = aluno_ou_404(bd, aluno_id)
        semestres, geral, qtd = montar_boletim(notas_do_aluno(bd, aluno["_id"]))
        return {"aluno": _aluno_json(aluno), "media_geral": geral, "semestres_com_media": qtd,
                "semestres": [{"semestre": n, "media": m, "disciplinas": [_nota_json(d) for d in discs]}
                              for n, discs, m in semestres]}

    @app.get("/turmas/ranking", tags=["Consultas"])
    def ranking(bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        return [{"posicao": i, **r} for i, r in enumerate(ranking_turmas(bd), start=1)]

    @app.get("/risco", tags=["Risco"])
    def risco_geral(turma: Optional[str] = None, bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        """Alerta de risco de todos os alunos (maior risco primeiro), com filtro opcional por turma."""
        saida = []
        for r in avaliar_todos(bd):
            if turma and r["turma"] != turma:
                continue
            r = dict(r)
            r["id"] = str(r.pop("aluno_id"))
            saida.append(r)
        return saida

    @app.get("/alunos/{aluno_id}/risco", tags=["Risco"])
    def risco_do_aluno(aluno_id: str, bd=Depends(obter_banco), _=Depends(exigir(*TODOS))):
        aluno = aluno_ou_404(bd, aluno_id)
        return {"aluno": _aluno_json(aluno), **avaliar_aluno(notas_do_aluno(bd, aluno["_id"]))}

    # ---------- usuários (só administrador) ----------
    @app.get("/usuarios", tags=["Usuários"])
    def listar_usuarios(bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        return [{"usuario": u["usuario"], "perfil": autenticacao.perfil_do(u),
                 "criado_em": u["data_cadastro"].isoformat() if u.get("data_cadastro") else None}
                for u in autenticacao.listar_usuarios(bd)]

    @app.post("/usuarios", status_code=201, tags=["Usuários"])
    def criar_usuario(dados: UsuarioIn, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        """Cria professor ou consulta (no máximo 3 além do administrador)."""
        try:
            novo = autenticacao.criar_usuario(bd, dados.usuario, dados.senha, dados.perfil)
        except ValueError as erro:
            raise HTTPException(422, str(erro))
        except autenticacao.LimiteUsuariosError as erro:
            raise HTTPException(status.HTTP_409_CONFLICT, str(erro))
        except DuplicateKeyError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esse usuário já existe.")
        return {"usuario": novo["usuario"], "perfil": novo["perfil"]}

    @app.put("/usuarios/{usuario}/senha", tags=["Usuários"])
    def trocar_senha(usuario: str, dados: SenhaIn, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        try:
            existe = autenticacao.trocar_senha(bd, usuario, dados.senha)
        except ValueError as erro:
            raise HTTPException(422, str(erro))
        if not existe:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
        return {"usuario": usuario.strip().lower(), "senha_alterada": True}

    @app.delete("/usuarios/{usuario}", status_code=204, tags=["Usuários"])
    def excluir_usuario(usuario: str, bd=Depends(obter_banco), _=Depends(exigir(ADMIN))):
        try:
            existia = autenticacao.excluir_usuario(bd, usuario)
        except PermissionError as erro:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(erro))
        if not existia:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
        return Response(status_code=204)

    return app


app = criar_app()  # `uvicorn api:app` (conecta ao MongoDB ao iniciar)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "127.0.0.1")  # só este computador; use 0.0.0.0 apenas se souber o que faz
    porta = int(os.getenv("API_PORT", "8000"))
    if "--demo" in sys.argv:
        import demo  # banco em memória com dados de exemplo (precisa de mongomock)
        uvicorn.run(criar_app(demo.montar_banco()), host=host, port=porta)
    else:
        uvicorn.run(app, host=host, port=porta)

