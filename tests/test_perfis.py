"""O que cada perfil enxerga no menu do terminal (a tela é conferida à parte, com janela)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import autenticacao  # noqa: E402
import interface  # noqa: E402


class TestMenuPorPerfil(unittest.TestCase):
    def opcoes(self, perfil):
        return {c for c, _ in interface.OPCOES if interface.opcao_permitida(c, perfil)}

    def test_professor_so_lanca_notas_e_consulta(self):
        # 3 lançar notas, 5 relatório do aluno, 6 ranking, 7 alerta de risco
        self.assertEqual(self.opcoes(autenticacao.PERFIL_PROFESSOR), {"3", "5", "6", "7"})

    def test_administrador_faz_tudo(self):
        self.assertEqual(self.opcoes(autenticacao.PERFIL_ADMIN), {c for c, _ in interface.OPCOES})

    def test_consulta_so_visualiza(self):
        self.assertEqual(self.opcoes(autenticacao.PERFIL_CONSULTA), {"4", "5", "6", "7"})


if __name__ == "__main__":
    unittest.main()
