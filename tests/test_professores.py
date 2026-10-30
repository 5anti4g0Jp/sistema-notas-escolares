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
