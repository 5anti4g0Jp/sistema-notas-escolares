"""Testes do resumo por IA (a chamada ao Gemini é simulada; não usa internet nem chave real)."""

import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import calculos  # noqa: E402
import resumo_ia  # noqa: E402

DADOS = [
    {"disciplina": "Matemática - Prof. Ana Lima", "semestre": 1, "avg": 8, "avi": 9, "avc": None},
    {"disciplina": "Português", "semestre": 1, "avg": 6, "avi": 5, "avc": 7},
]


def resposta(corpo):
    return io.BytesIO(json.dumps(corpo).encode("utf-8"))


class TestResumoIA(unittest.TestCase):
    def setUp(self):
        self.semestres, self.geral, _ = calculos.montar_boletim(DADOS)
        patch = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "chave-falsa"})
        patch.start()
        self.addCleanup(patch.stop)

    def test_pedido_nao_leva_professor(self):
        texto = resumo_ia.montar_pedido(self.semestres, self.geral)
        self.assertIn("Matemática", texto)
        self.assertIn("Português", texto)
        self.assertNotIn("Ana Lima", texto)
        self.assertNotIn("Prof.", texto)

    def test_sem_chave_da_erro_claro(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}), \
                mock.patch.object(resumo_ia, "ARQUIVO_CHAVE", resumo_ia.Path("/nao/existe.txt")):
            with self.assertRaises(resumo_ia.ResumoIAError):
                resumo_ia.gerar_resumo(self.semestres, self.geral)

    def test_resumo_devolve_o_texto_e_manda_a_chave_no_cabecalho(self):
        corpo = {"candidates": [{"content": {"parts": [{"text": "Bom aluno. "}, {"text": "Atenção a Português."}]}}]}
        with mock.patch("urllib.request.urlopen", return_value=resposta(corpo)) as abrir:
            texto = resumo_ia.gerar_resumo(self.semestres, self.geral)
        self.assertEqual(texto, "Bom aluno. Atenção a Português.")
        pedido = abrir.call_args.args[0]
        self.assertEqual(pedido.get_header("X-goog-api-key"), "chave-falsa")
        self.assertNotIn("chave-falsa", pedido.full_url)  # a chave nunca vai na URL

    def test_erros_viram_mensagens_sem_vazar_a_chave(self):
        casos = {403: "recusou", 429: "Limite", 500: "erro 500"}
        for codigo, trecho in casos.items():
            erro = urllib.error.HTTPError("u", codigo, "x", {}, None)
            with mock.patch("urllib.request.urlopen", side_effect=erro):
                with self.assertRaises(resumo_ia.ResumoIAError) as ctx:
                    resumo_ia.gerar_resumo(self.semestres, self.geral)
            self.assertIn(trecho, str(ctx.exception))
            self.assertNotIn("chave-falsa", str(ctx.exception))

    def test_sem_internet_e_resposta_vazia(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede")):
            with self.assertRaises(resumo_ia.ResumoIAError):
                resumo_ia.gerar_resumo(self.semestres, self.geral)
        for corpo in ({}, {"candidates": []}, {"candidates": [{"content": {"parts": [{"text": " "}]}}]}):
            with mock.patch("urllib.request.urlopen", return_value=resposta(corpo)):
                with self.assertRaises(resumo_ia.ResumoIAError):
                    resumo_ia.gerar_resumo(self.semestres, self.geral)


if __name__ == "__main__":
    unittest.main()
