"""Testes do visual (cantos arredondados e paleta). Precisam de Tkinter e de uma tela (xvfb-run no Linux)."""

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
    import tema


@unittest.skipUnless(TEM_TELA, "sem Tkinter ou sem tela disponível")
class TestTema(unittest.TestCase):
    def setUp(self):
        self.raiz = tk.Tk()
        self.addCleanup(self.raiz.destroy)

    def test_retangulo_arredondado_tem_cantos_do_fundo_e_centro_do_preenchimento(self):
        img = tema.retangulo_arredondado(self.raiz, 24, 9, "#0071E3", "#F2F2F7")
        self.assertEqual(img.get(0, 0), (0xF2, 0xF2, 0xF7))      # canto: fundo (arredondado)
        self.assertEqual(img.get(12, 12), (0x00, 0x71, 0xE3))    # centro: cor do botão
        self.assertEqual(img.get(12, 0)[2] > 0x80, True)         # meio da borda superior já é do botão

    def test_borda_fica_com_a_cor_da_borda(self):
        img = tema.retangulo_arredondado(self.raiz, 24, 9, "#FFFFFF", "#F2F2F7", 1, "#D1D1D6")
        self.assertEqual(img.get(12, 12), (255, 255, 255))
        self.assertNotEqual(img.get(12, 0), (255, 255, 255))     # a 1ª linha é borda, não branco

    def test_aplicar_tema_cria_fontes_e_guarda_as_imagens(self):
        tema.aplicar_tema(self.raiz)
        self.assertGreaterEqual(len(self.raiz.imagens_tema), 10)
        for nome in tema.FONTES:
            self.assertIn(nome, self.raiz.tk.call("font", "names"))

    def test_aplicar_tema_em_duas_janelas_ao_mesmo_tempo(self):
        """Login e tela principal nunca coexistem, mas outra janela aberta não pode quebrar o tema."""
        tema.aplicar_tema(self.raiz)
        outra = tk.Tk()
        self.addCleanup(outra.destroy)
        tema.aplicar_tema(outra)


if __name__ == "__main__":
    unittest.main()
