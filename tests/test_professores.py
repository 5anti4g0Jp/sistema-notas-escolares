"""Testes das regras de professores e alocações (usa mongomock, sem Atlas)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mongomock  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

import banco as modulo_banco  # noqa: E402
import calculos  # noqa: E402
import professores  # noqa: E402


class TestProfessores(unittest.TestCase):
    def setUp(self):
        self.banco = mongomock.MongoClient()["teste"]
        modulo_banco.criar_indices(self.banco)
        ins = lambda nome, cod: self.banco.disciplinas.insert_one(  # noqa: E731
            {"nome": nome, "codigo": cod, "carga_horaria": 60}).inserted_id
        self.poo, self.fisica = ins("POO", "POO"), ins("Educação Física", "EDF")
        self.ana = professores.criar_professor(self.banco, "Ana", [self.poo])
        self.beto = professores.criar_professor(self.banco, "Beto", [self.poo, self.fisica])

    def test_professor_de_poo_nao_da_educacao_fisica(self):
        with self.assertRaises(professores.RegraError):
            professores.alocar(self.banco, self.ana, self.fisica, 2026, "Turma A")
        self.assertEqual(self.banco.alocacoes.count_documents({}), 0)

    def test_mesmo_professor_em_varias_turmas(self):
        for turma in ("Turma A", "Turma B", "Turma C"):
            professores.alocar(self.banco, self.ana, self.poo, 2026, turma)
        self.assertEqual(self.banco.alocacoes.count_documents({"professor_id": self.ana}), 3)

    def test_mesma_turma_e_disciplina_com_professores_diferentes(self):
        professores.alocar(self.banco, self.ana, self.poo, 2026, "Turma A")
        professores.alocar(self.banco, self.beto, self.poo, 2026, "Turma A")
        rotulos = [r for _, _, r in professores.opcoes_de_lancamento(self.banco, "Turma A")]
        self.assertEqual(rotulos, ["POO - Prof. Ana", "POO - Prof. Beto"])

    def test_vinculo_repetido_e_recusado(self):
        professores.alocar(self.banco, self.ana, self.poo, 2026, "Turma A")
        with self.assertRaises(DuplicateKeyError):
            professores.alocar(self.banco, self.ana, self.poo, 2026, "Turma A")

    def test_nome_de_professor_unico_sem_diferenciar_maiusculas(self):
        with self.assertRaises(DuplicateKeyError):
            professores.criar_professor(self.banco, "ana", [self.poo])

    def test_nao_tira_habilitacao_em_uso(self):
        professores.alocar(self.banco, self.beto, self.fisica, 2026, "Turma A")
        with self.assertRaises(professores.RegraError):
            professores.atualizar_professor(self.banco, self.beto, "Beto", [self.poo])

    def test_turma_sem_alocacao_continua_por_disciplina(self):
        rotulos = [r for _, p, r in professores.opcoes_de_lancamento(self.banco, "Turma Z")]
        self.assertEqual(rotulos, ["EDF - Educação Física", "POO - POO"])

    def test_nota_do_mesmo_aluno_com_dois_professores_nao_se_mistura(self):
        aluno = self.banco.alunos.insert_one({"nome": "X", "matricula": "1", "turma": "Turma A"}).inserted_id
        base = {"aluno_id": aluno, "disciplina_id": self.poo, "semestre": 1}
        self.banco.notas.insert_one({**base, "professor_id": self.ana, "avg": 8, "avi": 8, "avc": None})
        self.banco.notas.insert_one({**base, "professor_id": self.beto, "avg": 6, "avi": 6, "avc": None})
        with self.assertRaises(DuplicateKeyError):  # mesma nota, mesmo professor
            self.banco.notas.insert_one({**base, "professor_id": self.ana, "avg": 1})
        disciplinas = [d["disciplina"] for d in calculos.notas_do_aluno(self.banco, aluno)]
        self.assertEqual(disciplinas, ["POO - Prof. Ana", "POO - Prof. Beto"])

    def test_nota_antiga_sem_professor_continua_aparecendo(self):
        aluno = self.banco.alunos.insert_one({"nome": "X", "matricula": "1", "turma": "Turma A"}).inserted_id
        self.banco.notas.insert_one({"aluno_id": aluno, "disciplina_id": self.poo, "semestre": 1,
                                     "avg": 7, "avi": 7, "avc": None})
        self.assertEqual([d["disciplina"] for d in calculos.notas_do_aluno(self.banco, aluno)], ["POO"])

    def test_professor_com_notas_nao_pode_ser_excluido(self):
        aluno = self.banco.alunos.insert_one({"nome": "X", "matricula": "1", "turma": "Turma A"}).inserted_id
        self.banco.notas.insert_one({"aluno_id": aluno, "disciplina_id": self.poo, "semestre": 1,
                                     "professor_id": self.ana, "avg": 7})
        with self.assertRaises(professores.RegraError):
            professores.excluir_professor(self.banco, self.ana)


if __name__ == "__main__":
    unittest.main()


try:
    from fastapi.testclient import TestClient
except ImportError:  # sem fastapi/httpx instalados
    TestClient = None

SENHA = "Senha12345"


@unittest.skipIf(TestClient is None, "instale fastapi, httpx e pyjwt para testar a API")
class TestApiProfessores(unittest.TestCase):
    """A API não pode contornar as regras de professor, nem apagar a nota de outro professor."""

    def setUp(self):
        import api
        self.banco = mongomock.MongoClient()["api_prof"]
        modulo_banco.criar_indices(self.banco)
        self.c = TestClient(api.criar_app(self.banco))
        self.c.__enter__()
        self.addCleanup(self.c.__exit__, None, None, None)
        self.c.post("/primeiro-acesso", json={"usuario": "admin", "senha": SENHA})
        self.h = self.entrar("admin", SENHA)
        self.poo = self.c.post("/disciplinas", json={"nome": "POO", "codigo": "POO", "carga_horaria": 60},
                               headers=self.h).json()["id"]
        self.edf = self.c.post("/disciplinas", json={"nome": "Ed Fisica", "codigo": "EDF", "carga_horaria": 40},
                               headers=self.h).json()["id"]
        self.aluno = self.c.post("/alunos", json={"nome": "Ze", "matricula": "1", "turma": "Turma A"},
                                 headers=self.h).json()["id"]
        from bson import ObjectId
        self.ana = professores.criar_professor(self.banco, "Ana", [ObjectId(self.poo)])
        self.beto = professores.criar_professor(self.banco, "Beto", [ObjectId(self.poo)])
        self.oid = ObjectId

    def entrar(self, usuario, senha):
        token = self.c.post("/login", json={"usuario": usuario, "senha": senha}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def lancar(self, disciplina, professor=None, **notas):
        url = f"/alunos/{self.aluno}/notas/{disciplina}/1"
        if professor:
            url += f"?professor_id={professor}"
        return self.c.put(url, json=notas or {"avg": 9, "avi": 9}, headers=self.h)

    def test_disciplina_fora_da_turma_e_recusada(self):
        professores.alocar(self.banco, self.ana, self.oid(self.poo), 2026, "Turma A")
        self.assertEqual(self.lancar(self.edf).status_code, 409)
        self.assertEqual(self.banco.notas.count_documents({}), 0)

    def test_nota_sai_com_o_professor_da_turma(self):
        professores.alocar(self.banco, self.ana, self.oid(self.poo), 2026, "Turma A")
        self.assertEqual(self.lancar(self.poo).status_code, 200)
        self.assertEqual(self.banco.notas.find_one()["professor_id"], self.ana)

    def test_dois_professores_exigem_escolha_e_nao_se_sobrescrevem(self):
        for prof in (self.ana, self.beto):
            professores.alocar(self.banco, prof, self.oid(self.poo), 2026, "Turma A")
        self.assertEqual(self.lancar(self.poo).status_code, 409)  # ambíguo
        self.assertEqual(self.lancar(self.poo, str(self.ana), avg=9, avi=9).status_code, 200)
        self.assertEqual(self.lancar(self.poo, str(self.beto), avg=5, avi=5).status_code, 200)
        self.assertEqual(self.banco.notas.count_documents({}), 2)  # a do Beto não apagou a da Ana

    def test_professor_de_outra_turma_e_recusado(self):
        professores.alocar(self.banco, self.ana, self.oid(self.poo), 2026, "Turma A")
        self.assertEqual(self.lancar(self.poo, str(self.beto)).status_code, 409)

    def test_turma_sem_alocacao_continua_lancando(self):
        self.assertEqual(self.lancar(self.poo).status_code, 200)
        self.assertEqual(self.lancar(self.poo, avg=7, avi=7).status_code, 200)  # atualiza, não duplica
        self.assertEqual(self.banco.notas.count_documents({}), 1)

    def test_excluir_disciplina_limpa_habilitacao_e_alocacao(self):
        professores.alocar(self.banco, self.ana, self.oid(self.poo), 2026, "Turma A")
        self.c.delete(f"/disciplinas/{self.poo}", headers=self.h)
        self.assertEqual(self.banco.alocacoes.count_documents({}), 0)
        self.assertEqual(self.banco.professores.find_one({"_id": self.ana})["disciplinas"], [])

    def test_token_antigo_morre_quando_a_senha_muda(self):
        self.c.post("/usuarios", json={"usuario": "prof", "senha": "abc12345", "perfil": "professor"},
                    headers=self.h)
        antigo = self.entrar("prof", "abc12345")
        self.assertEqual(self.c.get("/me", headers=antigo).status_code, 200)
        import time
        time.sleep(1.1)  # o token guarda o horário em segundos
        self.c.put("/usuarios/prof/senha", json={"senha": "nova12345"}, headers=self.h)
        self.assertEqual(self.c.get("/me", headers=antigo).status_code, 401)
        self.assertEqual(self.c.get("/me", headers=self.entrar("prof", "nova12345")).status_code, 200)


class TestLoginSeguro(unittest.TestCase):
    """Bloqueio por origem e hash de senha com mais iterações (contas antigas são atualizadas)."""

    def setUp(self):
        import autenticacao
        self.aut = autenticacao
        self.banco = mongomock.MongoClient()["login"]
        modulo_banco.criar_indices(self.banco)
        autenticacao.criar_admin(self.banco, "admin", "senha1234")

    def errar(self, usuario, origem, vezes):
        for _ in range(vezes):
            self.assertIsNone(self.aut.autenticar(self.banco, usuario, "errada123", origem))

    def test_quem_erra_de_um_endereco_nao_bloqueia_o_admin_de_outro(self):
        self.errar("admin", "1.1.1.1", self.aut.MAX_FALHAS)
        with self.assertRaises(self.aut.BloqueadoError):
            self.aut.autenticar(self.banco, "admin", "senha1234", "1.1.1.1")
        self.assertIsNotNone(self.aut.autenticar(self.banco, "admin", "senha1234", "2.2.2.2"))

    def test_origem_que_chuta_muitos_usuarios_e_barrada_e_o_lixo_tem_limite(self):
        for i in range(self.aut.MAX_FALHAS_POR_ORIGEM):
            self.assertIsNone(self.aut.autenticar(self.banco, f"fantasma{i}", "x1234567", "9.9.9.9"))
        with self.assertRaises(self.aut.BloqueadoError):
            self.aut.autenticar(self.banco, "admin", "senha1234", "9.9.9.9")  # nem o usuário real entra
        registros = self.banco.tentativas_login.count_documents({})
        self.assertLessEqual(registros, self.aut.MAX_FALHAS_POR_ORIGEM + 1)
        self.assertIsNotNone(self.aut.autenticar(self.banco, "admin", "senha1234", "2.2.2.2"))

    def test_sem_origem_continua_bloqueando_por_usuario(self):
        self.errar("admin", None, self.aut.MAX_FALHAS)
        with self.assertRaises(self.aut.BloqueadoError):
            self.aut.autenticar(self.banco, "admin", "senha1234")

    def test_trocar_senha_libera_o_bloqueio_de_todas_as_origens(self):
        self.errar("admin", "1.1.1.1", self.aut.MAX_FALHAS)
        self.aut.trocar_senha(self.banco, "admin", "nova12345")
        self.assertIsNotNone(self.aut.autenticar(self.banco, "admin", "nova12345", "1.1.1.1"))

    def test_conta_antiga_e_atualizada_no_login(self):
        salt, antigo = self.aut.gerar_hash("antiga123", iteracoes=self.aut.ITERACOES_ANTIGAS)
        self.banco.usuarios.insert_one({"usuario": "velho", "perfil": "consulta", "salt": salt,
                                        "hash": antigo})  # sem o campo "iteracoes"
        self.assertIsNotNone(self.aut.autenticar(self.banco, "velho", "antiga123"))
        doc = self.banco.usuarios.find_one({"usuario": "velho"})
        self.assertEqual(doc["iteracoes"], self.aut.ITERACOES)
        self.assertNotEqual(doc["hash"], antigo)
        self.assertIsNotNone(self.aut.autenticar(self.banco, "velho", "antiga123"))  # segue entrando

    def test_novas_contas_guardam_as_iteracoes(self):
        self.assertEqual(self.banco.usuarios.find_one({"usuario": "admin"})["iteracoes"], self.aut.ITERACOES)
        self.assertGreaterEqual(self.aut.ITERACOES, 600_000)
