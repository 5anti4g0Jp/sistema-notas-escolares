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


if __name__ == "__main__":
    unittest.main()
