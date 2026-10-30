"""Testes da API REST (FastAPI + mongomock; não usa Atlas nem a internet)."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import mongomock
    from fastapi.testclient import TestClient
except ImportError:  # sem fastapi/httpx instalados
    TestClient = None

if TestClient:
    import api
    import banco as modulo_banco

SENHA = "Senha12345"


@unittest.skipIf(TestClient is None, "instale fastapi, httpx e pyjwt para testar a API")
class TestApi(unittest.TestCase):
    def setUp(self):
        self.banco = mongomock.MongoClient()["api"]
        modulo_banco.criar_indices(self.banco)
        self.c = TestClient(api.criar_app(self.banco))
        self.c.__enter__()
        self.addCleanup(self.c.__exit__, None, None, None)
        self.assertEqual(self.c.post("/primeiro-acesso", json={"usuario": "chefe", "senha": SENHA}).status_code, 201)
        self.admin = self.entrar("chefe")

    def entrar(self, usuario, senha=SENHA):
        r = self.c.post("/login", json={"usuario": usuario, "senha": senha})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def criar_perfil(self, nome, perfil):
        r = self.c.post("/usuarios", headers=self.admin, json={"usuario": nome, "senha": SENHA, "perfil": perfil})
        self.assertEqual(r.status_code, 201, r.text)
        return self.entrar(nome)

    def semear(self):
        """Um aluno, uma disciplina e notas em 2 semestres. Devolve (id_aluno, id_disciplina)."""
        a = self.c.post("/alunos", headers=self.admin,
                        json={"nome": "Ana Souza", "matricula": "1", "turma": "Turma A"}).json()["id"]
        d = self.c.post("/disciplinas", headers=self.admin,
                        json={"nome": "Matemática", "codigo": "MAT", "carga_horaria": 80}).json()["id"]
        for sem, avg, avi in ((1, 9, 9), (2, 4, 4)):
            r = self.c.put(f"/alunos/{a}/notas/{d}/{sem}", headers=self.admin, json={"avg": avg, "avi": avi})
            self.assertEqual(r.status_code, 200, r.text)
        return a, d

    # ----- acesso -----
    def test_sem_token_ou_token_invalido(self):
        self.assertEqual(self.c.get("/alunos").status_code, 401)
        self.assertEqual(self.c.get("/alunos", headers={"Authorization": "Bearer lixo"}).status_code, 401)
        self.assertEqual(self.c.get("/me", headers=self.admin).json(), {"usuario": "chefe", "perfil": "administrador"})

    def test_primeiro_acesso_so_uma_vez_e_login_errado(self):
        r = self.c.post("/primeiro-acesso", json={"usuario": "outro", "senha": SENHA})
        self.assertEqual(r.status_code, 409)
        r = self.c.post("/login", json={"usuario": "chefe", "senha": "errada12345"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("hash", r.text)

    def test_bloqueio_apos_cinco_tentativas(self):
        for _ in range(5):
            self.assertEqual(self.c.post("/login", json={"usuario": "chefe", "senha": "errada12345"}).status_code, 401)
        r = self.c.post("/login", json={"usuario": "chefe", "senha": SENHA})
        self.assertEqual(r.status_code, 429)
        self.assertIn("retry-after", r.headers)

    def test_senha_fraca_no_primeiro_acesso(self):
        outro = TestClient(api.criar_app(mongomock.MongoClient()["vazio"]))
        with outro:
            self.assertEqual(outro.post("/primeiro-acesso", json={"usuario": "x", "senha": "curta"}).status_code, 422)

    # ----- alunos e disciplinas (administrador) -----
    def test_crud_de_alunos_com_filtros_e_cascata(self):
        a, d = self.semear()
        self.assertEqual(self.c.post("/alunos", headers=self.admin,
                                     json={"nome": "Dup", "matricula": "1", "turma": "B"}).status_code, 409)
        self.c.post("/alunos", headers=self.admin, json={"nome": "Beto", "matricula": "2", "turma": "Turma B"})
        self.assertEqual([x["nome"] for x in self.c.get("/alunos", headers=self.admin).json()], ["Ana Souza", "Beto"])
        self.assertEqual([x["nome"] for x in self.c.get("/alunos?turma=Turma B", headers=self.admin).json()], ["Beto"])
        self.assertEqual([x["nome"] for x in self.c.get("/alunos?busca=ANA", headers=self.admin).json()], ["Ana Souza"])
        r = self.c.put(f"/alunos/{a}", headers=self.admin, json={"nome": "Ana S.", "matricula": "1", "turma": "Turma C"})
        self.assertEqual(r.json()["turma"], "Turma C")
        self.assertEqual(self.c.delete(f"/alunos/{a}", headers=self.admin).status_code, 204)
        self.assertEqual(self.banco.notas.count_documents({}), 0)           # notas do aluno apagadas junto
        self.assertEqual(self.c.get(f"/alunos/{a}", headers=self.admin).status_code, 404)
        self.assertEqual(self.c.get("/alunos/nao-e-um-id", headers=self.admin).status_code, 404)

    def test_validacao_de_entrada(self):
        r = self.c.post("/alunos", headers=self.admin, json={"nome": "", "matricula": "1", "turma": "A"})
        self.assertEqual(r.status_code, 422)
        r = self.c.post("/disciplinas", headers=self.admin, json={"nome": "X", "codigo": "X", "carga_horaria": 0})
        self.assertEqual(r.status_code, 422)

    def test_disciplinas_crud_e_cascata(self):
        a, d = self.semear()
        self.assertEqual(self.c.post("/disciplinas", headers=self.admin,
                                     json={"nome": "Outra", "codigo": "MAT", "carga_horaria": 10}).status_code, 409)
        r = self.c.put(f"/disciplinas/{d}", headers=self.admin, json={"nome": "Mat II", "codigo": "MAT", "carga_horaria": 90})
        self.assertEqual(r.json()["nome"], "Mat II")
        self.assertEqual(self.c.delete(f"/disciplinas/{d}", headers=self.admin).status_code, 204)
        self.assertEqual(self.banco.notas.count_documents({}), 0)
        self.assertEqual(self.c.delete(f"/disciplinas/{d}", headers=self.admin).status_code, 404)

    # ----- notas e consultas -----
    def test_validacao_das_notas(self):
        a, d = self.semear()
        url = f"/alunos/{a}/notas/{d}"
        self.assertEqual(self.c.put(f"{url}/1", headers=self.admin, json={"avg": 11}).status_code, 422)
        self.assertEqual(self.c.put(f"{url}/1", headers=self.admin, json={"avg": -1}).status_code, 422)
        self.assertEqual(self.c.put(f"{url}/5", headers=self.admin, json={"avg": 5}).status_code, 422)
        self.assertEqual(self.c.put(f"{url}/0", headers=self.admin, json={"avg": 5}).status_code, 422)
        self.assertEqual(self.c.put(f"{url}/1", headers=self.admin, json={}).status_code, 422)
        self.assertEqual(self.c.put(f"/alunos/{a}/notas/000000000000000000000000/1", headers=self.admin,
                                    json={"avg": 5}).status_code, 404)

    def test_lancar_atualiza_e_calcula_a_media(self):
        a, d = self.semear()
        r = self.c.put(f"/alunos/{a}/notas/{d}/3", headers=self.admin, json={"avg": 4, "avi": 8, "avc": 10})
        self.assertEqual(r.json()["media"], 9.0)                            # duas maiores: (10 + 8) / 2
        r = self.c.put(f"/alunos/{a}/notas/{d}/3", headers=self.admin, json={"avg": 6, "avi": 6})
        self.assertEqual(r.json()["media"], 6.0)
        self.assertEqual(self.banco.notas.count_documents({"semestre": 3}), 1)  # atualizou, não duplicou

    def test_boletim_ranking_e_risco(self):
        a, d = self.semear()
        b = self.c.get(f"/alunos/{a}/boletim", headers=self.admin).json()
        self.assertEqual([s["media"] for s in b["semestres"]], [9.0, 4.0, None, None])
        self.assertEqual((b["media_geral"], b["semestres_com_media"]), (6.5, 2))
        self.assertEqual(self.c.get("/turmas/ranking", headers=self.admin).json()[0]["turma"], "Turma A")
        risco = self.c.get(f"/alunos/{a}/risco", headers=self.admin).json()
        self.assertEqual(risco["nivel"], "médio")
        lista = self.c.get("/risco?turma=Turma A", headers=self.admin).json()
        self.assertEqual(len(lista), 1)
        self.assertNotIn("aluno_id", lista[0])
        self.assertEqual(self.c.get("/risco?turma=Inexistente", headers=self.admin).json(), [])

    # ----- perfis -----
    def test_perfis_professor_e_consulta(self):
        a, d = self.semear()
        prof = self.criar_perfil("prof", "professor")
        cons = self.criar_perfil("cons", "consulta")
        # professor: vê tudo e lança notas; não cadastra nem gerencia usuários
        self.assertEqual(self.c.get("/alunos", headers=prof).status_code, 200)
        self.assertEqual(self.c.put(f"/alunos/{a}/notas/{d}/3", headers=prof, json={"avg": 8, "avi": 8}).status_code, 200)
        self.assertEqual(self.c.post("/alunos", headers=prof,
                                     json={"nome": "X", "matricula": "9", "turma": "A"}).status_code, 403)
        self.assertEqual(self.c.delete(f"/alunos/{a}", headers=prof).status_code, 403)
        self.assertEqual(self.c.get("/usuarios", headers=prof).status_code, 403)
        # consulta: só leitura
        for caminho in (f"/alunos/{a}/boletim", "/risco", "/turmas/ranking", "/disciplinas"):
            self.assertEqual(self.c.get(caminho, headers=cons).status_code, 200, caminho)
        self.assertEqual(self.c.put(f"/alunos/{a}/notas/{d}/3", headers=cons, json={"avg": 8}).status_code, 403)
        self.assertEqual(self.c.post("/disciplinas", headers=cons,
                                     json={"nome": "X", "codigo": "X", "carga_horaria": 1}).status_code, 403)

    # ----- usuários -----
    def test_limite_de_tres_usuarios_e_gerenciamento(self):
        for i in range(3):
            self.criar_perfil(f"user{i}", "professor")
        r = self.c.post("/usuarios", headers=self.admin, json={"usuario": "quarto", "senha": SENHA, "perfil": "consulta"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.c.post("/usuarios", headers=self.admin,
                                     json={"usuario": "user0", "senha": SENHA, "perfil": "consulta"}).status_code, 409)
        self.assertEqual(self.c.post("/usuarios", headers=self.admin,
                                     json={"usuario": "novo", "senha": SENHA, "perfil": "administrador"}).status_code, 422)
        lista = self.c.get("/usuarios", headers=self.admin).json()
        self.assertEqual([u["usuario"] for u in lista], ["chefe", "user0", "user1", "user2"])
        self.assertTrue(all("hash" not in u and "salt" not in u for u in lista))
        self.assertEqual(self.c.put("/usuarios/user1/senha", headers=self.admin, json={"senha": "Nova1234567"}).status_code, 200)
        self.assertEqual(self.c.put("/usuarios/user1/senha", headers=self.admin, json={"senha": "fraca"}).status_code, 422)
        self.assertEqual(self.c.put("/usuarios/fantasma/senha", headers=self.admin, json={"senha": SENHA}).status_code, 404)
        self.assertEqual(self.c.delete("/usuarios/chefe", headers=self.admin).status_code, 403)
        self.assertEqual(self.c.delete("/usuarios/user2", headers=self.admin).status_code, 204)
        self.assertEqual(self.c.delete("/usuarios/user2", headers=self.admin).status_code, 404)

    def test_usuario_excluido_perde_o_acesso_na_hora(self):
        prof = self.criar_perfil("prof", "professor")
        self.assertEqual(self.c.get("/alunos", headers=prof).status_code, 200)
        self.c.delete("/usuarios/prof", headers=self.admin)
        self.assertEqual(self.c.get("/alunos", headers=prof).status_code, 401)



if __name__ == "__main__":
    unittest.main()
