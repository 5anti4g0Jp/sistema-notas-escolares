"""Visual do sistema, no estilo do iOS: paleta, fontes e widgets ttk com cantos arredondados.

O Tkinter não arredonda cantos sozinho. Aqui os botões, campos e abas ganham imagens pequenas de
retângulos arredondados (com bordas suavizadas) que o ttk estica por "9-slice". As imagens são
desenhadas contra o fundo da janela, então só valem sobre BG (o fundo de todas as telas).
"""

import math
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------- paleta (tudo que tem cor no programa sai daqui) ----------
BG = "#F2F2F7"          # fundo agrupado do iOS
CARTAO = "#FFFFFF"      # campos, tabelas e áreas de texto
TEXTO = "#1C1C1E"
MUDO = "#6C6C70"        # textos de apoio
ACENTO = "#0071E3"      # ação principal e destaques
ACENTO_ESCURO = "#0058B0"
BORDA = "#D1D1D6"       # separadores
FAIXA = "#E5E5EA"       # botões neutros, abas inativas e fundo da barra de carregamento
SELECAO = "#D6E8FF"
PERIGO = "#D70015"      # médias abaixo do mínimo e ações destrutivas
BOM = "#248A3D"

# nome -> (tamanho, peso). Fontes nomeadas valem para todos os widgets da janela.
FONTES = {
    "IosCorpo": (10, "normal"),
    "IosNegrito": (10, "bold"),
    "IosNegritoG": (11, "bold"),
    "IosPequeno": (9, "normal"),
    "IosPequenoNegrito": (9, "bold"),
    "IosLogin": (16, "bold"),
    "IosTitulo": (22, "bold"),
}
PREFERIDAS = ("SF Pro Text", "SF Pro Display", ".AppleSystemUIFont", "Helvetica Neue",
              "Segoe UI Variable Text", "Segoe UI", "Inter", "Roboto")


def _rgb(cor):
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def _mistura(a, b, t):
    """Mistura as cores a e b (tuplas RGB); t=0 dá a, t=1 dá b."""
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def retangulo_arredondado(janela, tamanho, raio, preenchimento, fundo, espessura=0, cor_borda=None, margem=0):
    """Imagem quadrada com um retângulo de cantos arredondados, suavizado contra `fundo`.

    `margem` deixa uma folga com a cor do fundo ao redor (separa abas vizinhas)."""
    fill, bg = _rgb(preenchimento), _rgb(fundo)
    borda = _rgb(cor_borda) if cor_borda else None
    meio = tamanho / 2
    metade = meio - margem
    linhas = []
    for y in range(tamanho):
        cores = []
        for x in range(tamanho):
            qx = abs(x + 0.5 - meio) - (metade - raio)
            qy = abs(y + 0.5 - meio) - (metade - raio)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - raio  # distância à borda
            fora = min(max(0.5 - d, 0.0), 1.0)
            if borda and espessura:
                dentro = min(max(0.5 - (d + espessura), 0.0), 1.0)
                rgb = _mistura(_mistura(bg, borda, fora), fill, dentro)
            else:
                rgb = _mistura(bg, fill, fora)
            cores.append("#%02x%02x%02x" % rgb)
        linhas.append("{" + " ".join(cores) + "}")
    imagem = tk.PhotoImage(master=janela, width=tamanho, height=tamanho)
    imagem.put(" ".join(linhas))
    return imagem


def _elemento(estilo, janela, nome, variantes, raio=9, margem=0, padding=(0, 0, 0, 0), fundo=BG):
    """Cria um elemento ttk feito de imagens. `variantes`: [(estado ou None, preenchimento, borda ou None)].

    A 1ª é a padrão; as demais valem quando o estado bate (a ordem decide quando vários batem)."""
    imagens = []
    for estado, preenchimento, borda in variantes:
        img = retangulo_arredondado(janela, 2 * (raio + margem) + 2, raio, preenchimento, fundo,
                                    1 if borda else 0, borda, margem)
        janela.imagens_tema.append(img)  # sem referência, o Tk apaga a imagem
        imagens.append((estado, img))
    estilo.element_create(nome, "image", imagens[0][1], *[(e, i) for e, i in imagens[1:]],
                          border=(raio + margem,) * 4, padding=padding, sticky="nsew")


def _fontes(janela):
    """Cria as fontes nomeadas com a melhor família disponível (San Francisco no Mac, Segoe no Windows)."""
    disponiveis = set(tkfont.families(root=janela))
    familia = next((f for f in PREFERIDAS if f in disponiveis),
                   tkfont.nametofont("TkDefaultFont", root=janela).actual("family"))
    for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(nome, root=janela).configure(family=familia, size=10)
    for nome, (tamanho, peso) in FONTES.items():
        fonte = tkfont.Font(root=janela, name=nome, family=familia, size=tamanho, weight=peso, exists=False)
        janela.fontes_tema.append(fonte)


def aplicar_tema(janela):
    """Deixa a janela (e as que ela abrir) com o visual iOS."""
    janela.imagens_tema, janela.fontes_tema = [], []
    janela.configure(background=BG)
    _fontes(janela)
    e = ttk.Style(janela)
    e.theme_use("clam")
    base = dict(background=BG, foreground=TEXTO, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                troughcolor=FAIXA, focuscolor=BG)
    e.configure(".", font="IosCorpo", **base)
    e.configure("TFrame", background=BG)
    e.configure("TLabel", background=BG, foreground=TEXTO)
    e.configure("Titulo.TLabel", font="IosTitulo")
    e.configure("Sub.TLabel", foreground=MUDO)

    # grupos: título pequeno e cinza, sem moldura pesada
    e.configure("TLabelframe", background=BG, bordercolor=BORDA, lightcolor=BORDA, darkcolor=BORDA,
                relief="flat", borderwidth=1)
    e.configure("TLabelframe.Label", background=BG, foreground=MUDO, font="IosPequenoNegrito")

    # abas: "pílulas" (azul a selecionada, cinza as outras)
    _elemento(e, janela, "Ios.aba", [
        (None, FAIXA, None), ("selected", ACENTO, None), ("active", "#D8D8DE", None)],
        raio=9, margem=3, padding=(0, 0, 0, 0))
    e.layout("TNotebook.Tab", [("Ios.aba", {"sticky": "nswe", "children": [
        ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
            ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    e.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 2, 0, 8))
    e.configure("TNotebook.Tab", padding=(14, 6), background=BG, foreground="#3A3A3C", borderwidth=0)
    e.map("TNotebook.Tab", foreground=[("selected", "white")], expand=[("selected", (0, 0, 0, 0))],
          padding=[("selected", (14, 6))])

    # botões: neutro (cinza), de ação (azul) e perigoso (texto vermelho); "Link" é só texto
    for estilo, normal, ativo, apertado, desativado, texto in (
            ("TButton", FAIXA, "#DADAE0", "#CDCDD4", "#EEEEF3", TEXTO),
            ("Acento.TButton", ACENTO, "#1A82EE", ACENTO_ESCURO, "#9CC8F5", "white"),
            ("Perigo.TButton", FAIXA, "#DADAE0", "#CDCDD4", "#EEEEF3", PERIGO)):
        nome = "Ios." + estilo.split(".")[0].lower()
        _elemento(e, janela, nome, [
            (None, normal, None), (("disabled",), desativado, None), (("pressed",), apertado, None),
            (("active",), ativo, None)], raio=9)
        e.layout(estilo, [(nome, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})]})])
        e.configure(estilo, padding=(14, 7), foreground=texto, anchor="center")
        e.map(estilo, foreground=[("disabled", "white" if estilo == "Acento.TButton" else "#9A9AA0")])
    e.layout("Link.TButton", [("Button.padding", {"sticky": "nswe", "children": [
        ("Button.label", {"sticky": "nswe"})]})])
    e.configure("Link.TButton", background=BG, foreground=ACENTO, padding=(10, 4), relief="flat")
    e.map("Link.TButton", foreground=[("pressed", ACENTO_ESCURO), ("active", "#3392F0"), ("disabled", "#9A9AA0")],
          background=[("active", BG), ("pressed", BG)])

    # campos: brancos, arredondados, com anel azul no foco
    _elemento(e, janela, "Ios.campo", [(None, CARTAO, BORDA), (("focus",), CARTAO, ACENTO)], raio=9,
              padding=(2, 3, 5, 3))  # folga: a seta não cobre o canto arredondado
    e.layout("TEntry", [("Ios.campo", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [("Entry.textarea", {"sticky": "nswe"})]})]})])
    e.layout("TCombobox", [("Ios.campo", {"sticky": "nswe", "children": [
        ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"})]})]})])
    e.layout("TSpinbox", [("Ios.campo", {"sticky": "nswe", "children": [
        ("null", {"side": "right", "sticky": "", "children": [
            ("Spinbox.uparrow", {"side": "top", "sticky": "e"}),
            ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"})]}),
        ("Spinbox.padding", {"sticky": "nswe", "children": [("Spinbox.textarea", {"sticky": "nswe"})]})]})])
    e.configure("TSpinbox", arrowcolor=MUDO, background=CARTAO, arrowsize=12, bordercolor=CARTAO,
                lightcolor=CARTAO, darkcolor=CARTAO)
    for campo in ("TEntry", "TCombobox", "TSpinbox"):
        e.configure(campo, fieldbackground=CARTAO, bordercolor=BORDA, padding=(8, 6))
    e.configure("TCombobox", arrowcolor=MUDO, background=CARTAO, arrowsize=16, bordercolor=CARTAO,
                lightcolor=CARTAO, darkcolor=CARTAO)
    e.map("TCombobox", background=[("active", CARTAO), ("pressed", CARTAO)],
          lightcolor=[("active", CARTAO)], darkcolor=[("active", CARTAO)])
    e.map("TCombobox", fieldbackground=[("readonly", CARTAO)], selectbackground=[("readonly", CARTAO)],
          selectforeground=[("readonly", TEXTO)], bordercolor=[("focus", CARTAO)])
    e.map("TEntry", bordercolor=[("focus", ACENTO)])
    janela.option_add("*TCombobox*Listbox.background", CARTAO)
    janela.option_add("*TCombobox*Listbox.foreground", TEXTO)
    janela.option_add("*TCombobox*Listbox.selectBackground", ACENTO)
    janela.option_add("*TCombobox*Listbox.selectForeground", "white")
    janela.option_add("*TCombobox*Listbox.font", "IosCorpo")

    # tabelas: brancas, linhas altas, cabeçalho discreto
    e.configure("Treeview", background=CARTAO, fieldbackground=CARTAO, foreground=TEXTO, rowheight=30,
                bordercolor=BORDA, lightcolor=CARTAO, darkcolor=CARTAO)
    e.map("Treeview", background=[("selected", SELECAO)], foreground=[("selected", TEXTO)])
    e.configure("Treeview.Heading", background="#F8F8FB", foreground=MUDO, relief="flat", padding=(8, 8),
                font="IosPequenoNegrito", bordercolor=BORDA, lightcolor="#F8F8FB", darkcolor="#F8F8FB")
    e.map("Treeview.Heading", background=[("active", "#F0F0F5")])

    # barra de rolagem fina, sem setas (como a do iOS)
    e.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    e.configure("Vertical.TScrollbar", background="#D9D9DE", troughcolor=CARTAO, bordercolor=CARTAO,
                lightcolor="#D9D9DE", darkcolor="#D9D9DE", arrowsize=9, gripcount=0)
    e.map("Vertical.TScrollbar", background=[("active", "#B8B8BE")], lightcolor=[("active", "#B8B8BE")],
          darkcolor=[("active", "#B8B8BE")])
