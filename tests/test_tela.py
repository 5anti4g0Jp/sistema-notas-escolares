"""Testes da janela principal. Precisam de Tkinter e de uma tela (no Linux sem monitor: xvfb-run)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import tkinter as tk
    raiz = tk.Tk()
    raiz.destroy()
    TEM_TELA = True
except Exception:  # sem tkinter ou sem display
    TEM_TELA = False

if TEM_TELA:
    import mongomock

    import autenticacao
    import banco as modulo_banco
    import tela


@unittest.skipUnless(TEM_TELA, "sem Tkinter ou sem tela disponível")
class TestTela(unittest.TestCase):
    def setUp(self):
        self.banco = mongomock.MongoClient()["tela"]
        modulo_banco.criar_indices(self.banco)

    def abas_visiveis(self, app):
        return [app.abas.tab(t, "text") for t in app.abas.tabs() if app.abas.tab(t, "state") != "hidden"]

    def test_tela_principal_abre_depois_do_login_fechar(self):
        """Fluxo do programa: o Login abre, fecha, e só então abre a tela principal."""
        login = tk.Tk()
        login.destroy()
        app = tela.App(self.banco, "ana", autenticacao.PERFIL_ADMIN)
        self.addCleanup(app.destroy)
        app.update()

    def test_imagens_da_tela_nao_dependem_de_outra_janela_aberta(self):
        """Com outra janela do Tk ainda aberta, a imagem da barra tem de pertencer à tela principal."""
        outra = tk.Tk()  # vira a janela "padrão" do Tkinter
        self.addCleanup(outra.destroy)
        app = tela.App(self.banco, "ana", autenticacao.PERFIL_ADMIN)  # já falhou com "pyimage2 doesn't exist"
        self.addCleanup(app.destroy)
        app.update()

    def test_professor_so_ve_lancar_notas_e_consultas(self):
        app = tela.App(self.banco, "rafael", autenticacao.PERFIL_PROFESSOR)
        self.addCleanup(app.destroy)
        app.update()
        self.assertEqual(self.abas_visiveis(app), list(tela.ABAS_DO_PROFESSOR))
        self.assertEqual(app.abas.tab(app.abas.select(), "text"), "Lançar notas")

    def test_administrador_ve_todas_as_abas(self):
        app = tela.App(self.banco, "chefe", autenticacao.PERFIL_ADMIN)
        self.addCleanup(app.destroy)
        app.update()
        self.assertEqual(len(self.abas_visiveis(app)), 9)
        self.assertIn("Usuários", self.abas_visiveis(app))


@unittest.skipUnless(TEM_TELA, "sem Tkinter ou sem tela disponível")
class TestCoresEResumo(unittest.TestCase):
    def test_media_abaixo_do_minimo_fica_vermelha(self):
        self.assertEqual(tela.tag_media(5.99), ("fraca",))
        self.assertEqual(tela.tag_media(6.0), ())  # no limite não é fraca (mesma regra do alerta de risco)
        self.assertEqual(tela.tag_media(None), ())
        self.assertEqual(tela.cor_media(4.0), tela.PERIGO)
        self.assertEqual(tela.cor_media(8.0), tela.BOM)
        self.assertEqual(tela.cor_media(None), tela.TEXTO)

    def preparar(self):
        banco = mongomock.MongoClient()["resumo"]
        modulo_banco.criar_indices(banco)
        app = tela.App(banco, "ana", autenticacao.PERFIL_ADMIN)
        self.addCleanup(app.destroy)
        app.update()
        return app

    def esperar(self, app, condicao, segundos=5):
        import time
        limite = time.time() + segundos
        while not condicao() and time.time() < limite:
            app.update()
            time.sleep(0.02)
        self.assertTrue(condicao())

    def test_janela_do_resumo_gera_e_mostra_o_texto(self):
        from unittest import mock
        app = self.preparar()
        with mock.patch.object(tela.resumo_ia, "gerar_resumo", return_value="Resumo de teste."):
            janela = tela.JanelaResumo(app, "Ana", [], 7.0)
            self.esperar(app, lambda: not janela.em_andamento)
        self.assertEqual(janela.texto.get("1.0", "end").strip(), "Resumo de teste.")
        self.assertEqual(str(janela.bt_gerar.cget("state")), "normal")
        self.assertFalse(janela.carregando.barra.winfo_ismapped())

    def test_erro_da_ia_aparece_na_janela(self):
        from unittest import mock
        app = self.preparar()
        erro = tela.resumo_ia.ResumoIAError("Chave do Gemini não encontrada.")
        with mock.patch.object(tela.resumo_ia, "gerar_resumo", side_effect=erro):
            janela = tela.JanelaResumo(app, "Ana", [], 7.0)
            self.esperar(app, lambda: not janela.em_andamento)
        self.assertIn("Chave do Gemini", janela.texto.get("1.0", "end"))

    def test_fechar_a_janela_no_meio_nao_da_erro(self):
        import time
        from unittest import mock
        app = self.preparar()
        with mock.patch.object(tela.resumo_ia, "gerar_resumo", side_effect=lambda *a: time.sleep(0.4) or "tarde"):
            janela = tela.JanelaResumo(app, "Ana", [], 7.0)
            app.update()
            janela.fechar()  # o resultado chega depois e tem de ser descartado em silêncio
            fim = time.time() + 1.0
            while time.time() < fim:
                app.update()
                time.sleep(0.02)
        self.assertFalse(janela.winfo_exists())


@unittest.skipUnless(TEM_TELA, "sem Tkinter ou sem tela disponível")
class TestAlertaDeRisco(unittest.TestCase):
    def setUp(self):
        import demo
        self.app = tela.App(demo.montar_banco(), "ana", autenticacao.PERFIL_ADMIN)
        self.addCleanup(self.app.destroy)
        self.app.update()

    def test_aluno_de_maior_risco_ja_vem_selecionado_com_todos_os_motivos(self):
        self.app.gerar_risco()
        self.app.update()
        r = self.app.risco_lista[0]  # a lista vem do maior para o menor risco
        self.assertEqual(self.app.tab_risco.selection(), (str(r["aluno_id"]),))
        detalhe = self.app.txt_risco.get("1.0", "end")
        self.assertIn(r["nome"], detalhe)
        for motivo in r["motivos"]:
            self.assertIn(motivo, detalhe)  # nada fica cortado no detalhe

    def test_texto_longo_na_tabela_termina_com_reticencias(self):
        self.assertEqual(tela.resumir("abc", 10), "abc")
        curto = tela.resumir("palavra " * 30, 20)
        self.assertEqual(len(curto), 20)
        self.assertTrue(curto.endswith("…"))

    def test_resumo_dos_motivos_mostra_o_primeiro_e_quantos_faltam(self):
        self.assertEqual(tela.resumo_motivos([]), "")
        self.assertEqual(tela.resumo_motivos(["Sem sinais de risco."]), "Sem sinais de risco.")
        r = tela.resumo_motivos(["Média geral próxima do limite (6.52).", "Média abaixo de 6 em: Informática.",
                                 "Queda forte (-3.80)."])
        self.assertEqual(r, "Média geral próxima do limite (6.52).  (+2)")
        self.assertTrue(tela.resumo_motivos(["x" * 200, "y"]).endswith("…  (+1)"))

    def test_escolher_outro_aluno_troca_o_detalhe(self):
        self.app.gerar_risco()
        self.app.update()
        outro = self.app.risco_lista[-1]
        self.app.tab_risco.selection_set(str(outro["aluno_id"]))
        self.app.update()
        self.assertIn(outro["nome"], self.app.txt_risco.get("1.0", "end"))

    def test_posicao_do_ranking_fica_centralizada(self):
        self.assertEqual(str(self.app.tab_rank.column("Posição", "anchor")), "center")


if __name__ == "__main__":
    unittest.main()
