"""Testes das regras de cálculo e da autenticação (usa mongomock, sem Atlas)."""

import json
import os
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mongomock  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

import autenticacao  # noqa: E402
import calculos  # noqa: E402
import risco  # noqa: E402


class TestCalculos(unittest.TestCase):
    def test_ler_nota(self):
        self.assertIsNone(calculos.ler_nota_opcional("  "))
        self.assertEqual(calculos.ler_nota_opcional("7,456"), 7.46)
        for ruim in ("11", "-1", "abc", "nan", "inf"):
            with self.assertRaises(ValueError):
                calculos.ler_nota_opcional(ruim)

    def test_media_duas_maiores(self):
        self.assertEqual(calculos.calcular_media([4, 8, 10]), 9.0)
        self.assertEqual(calculos.calcular_media([None, 6, 8]), 7.0)
        self.assertIsNone(calculos.calcular_media([None, 6, None]))

    def test_boletim_e_medias(self):
        dados = [
            {"disciplina": "Mat", "semestre": 1, "avg": 8, "avi": 10, "avc": None},  # 9
            {"disciplina": "Port", "semestre": 1, "avg": 6, "avi": 6, "avc": None},  # 6
            {"disciplina": "Mat", "semestre": 2, "avg": 7, "avi": 7, "avc": 3},      # 7
            {"disciplina": "Hist", "semestre": 2, "avg": 5, "avi": None, "avc": None},  # sem média
        ]
        semestres, geral, qtd = calculos.montar_boletim(dados)
        self.assertEqual([m for _, _, m in semestres], [7.5, 7.0, None, None])
        self.assertEqual((geral, qtd), (7.25, 2))
        self.assertEqual(calculos.medias_por_disciplina(dados), {"Mat": 8.0, "Port": 6.0})


class TestBanco(unittest.TestCase):
    def setUp(self):
        self.banco = mongomock.MongoClient()["teste"]

    def test_senha(self):
        self.assertIsNotNone(autenticacao.validar_senha("curta1"))
        self.assertIsNotNone(autenticacao.validar_senha("somenteletras"))
        self.assertIsNone(autenticacao.validar_senha("senha1234"))

    def test_primeiro_admin_so_uma_vez(self):
        autenticacao.criar_primeiro_admin(self.banco, "Admin", "senha1234")
        with self.assertRaises(PermissionError):
            autenticacao.criar_primeiro_admin(self.banco, "outro", "senha1234")
        with self.assertRaises(ValueError):
            autenticacao.criar_admin(self.banco, "x", "fraca")

    def test_login_e_bloqueio(self):
        autenticacao.criar_admin(self.banco, "admin", "senha1234")
        self.assertIsNotNone(autenticacao.autenticar(self.banco, " ADMIN ", "senha1234"))
        for _ in range(autenticacao.MAX_FALHAS):
            self.assertIsNone(autenticacao.autenticar(self.banco, "admin", "errada123"))
        with self.assertRaises(autenticacao.BloqueadoError) as ctx:
            autenticacao.autenticar(self.banco, "admin", "senha1234")  # nem a certa entra
        self.assertGreater(ctx.exception.segundos, 0)

        # passado o prazo, volta a funcionar e zera o registro
        self.banco.tentativas_login.update_one(
            {"_id": "admin"},
            {"$set": {"bloqueado_ate": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        self.assertIsNotNone(autenticacao.autenticar(self.banco, "admin", "senha1234"))
        self.assertIsNone(self.banco.tentativas_login.find_one({"_id": "admin"}))

    def test_usuario_inexistente_tambem_conta_falha(self):
        for _ in range(autenticacao.MAX_FALHAS):
            self.assertIsNone(autenticacao.autenticar(self.banco, "fantasma", "qualquer1"))
        with self.assertRaises(autenticacao.BloqueadoError):
            autenticacao.autenticar(self.banco, "fantasma", "qualquer1")

    def test_notas_e_ranking(self):
        a1 = self.banco.alunos.insert_one({"nome": "Ana", "turma": "A"}).inserted_id
        a2 = self.banco.alunos.insert_one({"nome": "Beto", "turma": "B"}).inserted_id
        mat = self.banco.disciplinas.insert_one({"nome": "Mat"}).inserted_id
        self.banco.notas.insert_many([
            {"aluno_id": a1, "disciplina_id": mat, "semestre": 1, "avg": 8, "avi": 10, "avc": None},
            {"aluno_id": a2, "disciplina_id": mat, "semestre": 1, "avg": 5, "avi": 7, "avc": None},
            {"aluno_id": a2, "disciplina_id": mat, "semestre": 2, "avg": 4, "avi": None, "avc": None},
            {"aluno_id": a1, "disciplina_id": mat, "bimestre": 1, "nota": 3},  # legado: ignorado
        ])
        dados = calculos.notas_do_aluno(self.banco, a1)
        self.assertEqual(len(dados), 1)
        self.assertEqual(dados[0]["disciplina"], "Mat")
        ranking = calculos.ranking_turmas(self.banco)
        self.assertEqual([(r["turma"], r["media"], r["alunos"], r["notas"]) for r in ranking],
                         [("A", 9.0, 1, 1), ("B", 6.0, 1, 1)])


class TestUsuarios(unittest.TestCase):
    SENHA = "Senha1234"

    def setUp(self):
        import banco as modulo_banco
        self.banco = mongomock.MongoClient()["usuarios"]
        modulo_banco.criar_indices(self.banco)  # como o sistema faz ao conectar (índice único de usuário)
        autenticacao.criar_primeiro_admin(self.banco, "chefe", self.SENHA)

    def test_admin_tem_perfil_e_contas_antigas_sao_admin(self):
        admin = autenticacao.autenticar(self.banco, "chefe", self.SENHA)
        self.assertEqual(autenticacao.perfil_do(admin), autenticacao.PERFIL_ADMIN)
        self.assertEqual(autenticacao.perfil_do({"usuario": "antigo"}), autenticacao.PERFIL_ADMIN)

    def test_limite_de_tres_usuarios_alem_do_admin(self):
        for i, perfil in enumerate(("professor", "consulta", "professor"), start=1):
            autenticacao.criar_usuario(self.banco, f"user{i}", self.SENHA, perfil)
        self.assertEqual(autenticacao.contar_extras(self.banco), 3)
        with self.assertRaises(autenticacao.LimiteUsuariosError):
            autenticacao.criar_usuario(self.banco, "user4", self.SENHA, "consulta")
        self.assertEqual(self.banco.usuarios.count_documents({}), 4)  # 1 admin + 3
        # excluir um libera uma vaga
        self.assertTrue(autenticacao.excluir_usuario(self.banco, "user2"))
        autenticacao.criar_usuario(self.banco, "user4", self.SENHA, "consulta")

    def test_nao_cria_segundo_admin_nem_perfil_invalido(self):
        for perfil in ("administrador", "chefe", ""):
            with self.assertRaises(ValueError):
                autenticacao.criar_usuario(self.banco, "novo", self.SENHA, perfil)
        self.assertEqual(autenticacao.contar_extras(self.banco), 0)

    def test_validacoes_de_nome_senha_e_duplicado(self):
        with self.assertRaises(ValueError):
            autenticacao.criar_usuario(self.banco, "  ", self.SENHA, "professor")
        with self.assertRaises(ValueError):
            autenticacao.criar_usuario(self.banco, "fraco", "curta", "professor")
        autenticacao.criar_usuario(self.banco, "Maria", self.SENHA, "professor")
        with self.assertRaises(DuplicateKeyError):
            autenticacao.criar_usuario(self.banco, "maria", self.SENHA, "consulta")

    def test_login_devolve_o_perfil(self):
        autenticacao.criar_usuario(self.banco, "prof", self.SENHA, "professor")
        doc = autenticacao.autenticar(self.banco, "prof", self.SENHA)
        self.assertEqual(autenticacao.perfil_do(doc), "professor")

    def test_trocar_senha_e_excluir(self):
        autenticacao.criar_usuario(self.banco, "prof", self.SENHA, "professor")
        self.assertTrue(autenticacao.trocar_senha(self.banco, "prof", "Nova12345"))
        self.assertIsNone(autenticacao.autenticar(self.banco, "prof", self.SENHA))
        self.assertIsNotNone(autenticacao.autenticar(self.banco, "prof", "Nova12345"))
        with self.assertRaises(ValueError):
            autenticacao.trocar_senha(self.banco, "prof", "fraca")
        self.assertFalse(autenticacao.trocar_senha(self.banco, "fantasma", "Nova12345"))
        self.assertTrue(autenticacao.excluir_usuario(self.banco, "prof"))
        self.assertFalse(autenticacao.excluir_usuario(self.banco, "prof"))

    def test_administrador_nao_pode_ser_excluido(self):
        with self.assertRaises(PermissionError):
            autenticacao.excluir_usuario(self.banco, "chefe")
        self.assertIsNotNone(autenticacao.autenticar(self.banco, "chefe", self.SENHA))

    def test_listar_usuarios_sem_segredos_e_admin_primeiro(self):
        autenticacao.criar_usuario(self.banco, "ana", self.SENHA, "consulta")
        lista = autenticacao.listar_usuarios(self.banco)
        self.assertEqual([u["usuario"] for u in lista], ["chefe", "ana"])
        self.assertTrue(all("hash" not in u and "salt" not in u for u in lista))

    def test_permissoes_do_menu_do_terminal(self):
        import interface
        admin, prof, cons = "administrador", "professor", "consulta"
        for opcao in "12345678":
            self.assertTrue(interface.opcao_permitida(opcao, admin))
        self.assertFalse(interface.opcao_permitida("1", prof))
        self.assertFalse(interface.opcao_permitida("2", prof))
        self.assertTrue(interface.opcao_permitida("3", prof))
        for opcao in "123":
            self.assertFalse(interface.opcao_permitida(opcao, cons))
        for opcao in "45678":
            self.assertTrue(interface.opcao_permitida(opcao, cons))


class TestRisco(unittest.TestCase):
    @staticmethod
    def nota(disc, sem, avg, avi, avc=None):
        return {"disciplina": disc, "semestre": sem, "avg": avg, "avi": avi, "avc": avc}

    def test_sem_dados(self):
        self.assertEqual(risco.avaliar_aluno([])["nivel"], "sem dados")
        self.assertEqual(risco.avaliar_aluno([self.nota("Mat", 1, 5, None)])["nivel"], "sem dados")

    def test_aluno_estavel_tem_risco_baixo(self):
        r = risco.avaliar_aluno([self.nota("Mat", 1, 8, 9), self.nota("Mat", 2, 8, 8)])
        self.assertEqual((r["nivel"], r["pontos"]), ("baixo", 0))
        self.assertEqual(r["motivos"], ["Sem sinais de risco."])

    def test_aluno_em_queda_tem_risco_alto(self):
        dados = [self.nota("Mat", 1, 9, 9), self.nota("Port", 1, 9, 9),
                 self.nota("Mat", 2, 4, 4), self.nota("Port", 2, 4, 5)]
        r = risco.avaliar_aluno(dados)  # média geral 6.6; fracas: 2; queda 4.5
        self.assertEqual(r["nivel"], "alto")
        self.assertEqual(r["pontos"], 12 + 20 + 25)
        self.assertEqual(len(r["motivos"]), 3)

    def test_pontuacao_limitada_a_100_e_ordem(self):
        banco = mongomock.MongoClient()["risco"]
        bom = banco.alunos.insert_one({"nome": "Bom", "matricula": "1", "turma": "A"}).inserted_id
        mau = banco.alunos.insert_one({"nome": "Mau", "matricula": "2", "turma": "A"}).inserted_id
        banco.alunos.insert_one({"nome": "Novo", "matricula": "3", "turma": "A"})
        mat = banco.disciplinas.insert_one({"nome": "Mat"}).inserted_id
        banco.notas.insert_many([
            {"aluno_id": bom, "disciplina_id": mat, "semestre": 1, "avg": 9, "avi": 9},
            {"aluno_id": mau, "disciplina_id": mat, "semestre": 1, "avg": 3, "avi": 2},
        ])
        resultado = risco.avaliar_todos(banco)
        self.assertEqual([r["nome"] for r in resultado], ["Mau", "Bom", "Novo"])
        self.assertEqual(resultado[0]["nivel"], "alto")
        self.assertEqual(resultado[2]["nivel"], "sem dados")
        self.assertLessEqual(resultado[0]["pontos"], 100)



if __name__ == "__main__":
    unittest.main()
