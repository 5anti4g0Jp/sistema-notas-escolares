"""Interface gráfica (Tkinter) do sistema de notas escolares.

Execute com: python tela.py
(a variável de ambiente MONGODB_URI precisa estar definida).
"""

import os
import queue
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from pymongo.errors import DuplicateKeyError, PyMongoError

import autenticacao
import professores
import resumo_ia
from banco import conectar_banco
from calculos import (PROVAS, SEMESTRES, calcular_media, fmt, ler_nota_opcional,
                      media_da_nota, medias_por_disciplina, montar_boletim,
                      notas_do_aluno, ranking_turmas)
from config import NOME_BANCO
from risco import NOTA_MINIMA, avaliar_aluno, avaliar_todos

# Paleta única da interface (tudo que tem cor no programa sai daqui)
BG = "#f3f5fa"        # fundo das janelas
CARTAO = "#ffffff"    # campos, tabelas e áreas de texto
TEXTO = "#1f2937"
MUDO = "#5b6475"      # textos de apoio
ACENTO = "#2f5bd8"    # ação principal e destaques
ACENTO_ESCURO = "#2449b3"
BORDA = "#c9d1e3"
FAIXA = "#e6ebf5"     # cabeçalhos, abas inativas e fundo da barra de carregamento
SELECAO = "#d6e2fb"
PERIGO = "#b3261e"    # médias abaixo do mínimo e ações destrutivas
BOM = "#1b6e3c"

TODAS_TURMAS = "Todas as turmas"
# O professor só lança notas e consulta; cadastros, vínculos e usuários nem aparecem para ele.
ABAS_DO_PROFESSOR = ("Lançar notas", "Boletim", "Ranking de turmas", "Alerta de risco")
COLUNAS_NOTAS = ("Disciplina", "Semestre", "AVG", "AVI", "AVC", "Média")
LARGURAS_NOTAS = (320, 90, 90, 90, 90, 100)


def aplicar_tema(janela):
    """Deixa todas as janelas com o mesmo visual (base clam, cores da paleta acima)."""
    janela.configure(background=BG)
    for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(nome, root=janela).configure(size=10)
    negrito = tkfont.nametofont("TkDefaultFont", root=janela).copy()
    negrito.configure(weight="bold")
    janela.fonte_negrito = negrito  # o Tk apaga a fonte se o Python a descartar; guardar na janela evita isso
    e = ttk.Style(janela)
    e.theme_use("clam")
    e.configure(".", background=BG, foreground=TEXTO, bordercolor=BORDA, lightcolor=BG, darkcolor=BG,
                troughcolor=FAIXA, focuscolor=ACENTO)
    e.configure("TFrame", background=BG)
    e.configure("TLabel", background=BG, foreground=TEXTO)
    e.configure("TLabelframe", background=BG, bordercolor=BORDA)
    e.configure("TLabelframe.Label", background=BG, foreground=ACENTO, font=negrito)
    e.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    e.configure("TNotebook.Tab", background=FAIXA, foreground=MUDO, padding=(14, 7), borderwidth=0)
    e.map("TNotebook.Tab", background=[("selected", BG), ("active", "#dde4f3")],
          foreground=[("selected", ACENTO)])
    e.configure("TButton", background=FAIXA, foreground=TEXTO, padding=(12, 6), bordercolor=BORDA,
                relief="flat")
    e.map("TButton", background=[("disabled", "#eceff5"), ("pressed", "#cfd8ec"), ("active", "#dbe3f4")],
          foreground=[("disabled", "#9aa3b5")])
    e.configure("Acento.TButton", background=ACENTO, foreground="white", bordercolor=ACENTO)
    e.map("Acento.TButton", background=[("disabled", "#a9b8e6"), ("pressed", ACENTO_ESCURO), ("active", "#3d68e0")],
          foreground=[("disabled", "white")], bordercolor=[("disabled", "#a9b8e6")])
    e.configure("Perigo.TButton", foreground=PERIGO)
    e.map("Perigo.TButton", foreground=[("disabled", "#9aa3b5")])
    for campo in ("TEntry", "TCombobox", "TSpinbox"):
        e.configure(campo, fieldbackground=CARTAO, bordercolor=BORDA, padding=4)
        e.map(campo, bordercolor=[("focus", ACENTO)])
    e.map("TCombobox", fieldbackground=[("readonly", CARTAO)], selectbackground=[("readonly", CARTAO)],
          selectforeground=[("readonly", TEXTO)])
    e.configure("Treeview", background=CARTAO, fieldbackground=CARTAO, foreground=TEXTO, rowheight=26,
                bordercolor=BORDA)
    e.map("Treeview", background=[("selected", SELECAO)], foreground=[("selected", TEXTO)])
    e.configure("Treeview.Heading", background=FAIXA, foreground=TEXTO, relief="flat", padding=(6, 6),
                font=negrito)
    e.map("Treeview.Heading", background=[("active", "#dbe3f4")])
    e.configure("TScrollbar", background="#c3cce0", troughcolor=FAIXA, bordercolor=BORDA, arrowcolor=MUDO)


def tag_media(media):
    """Tag de linha que pinta de vermelho a média abaixo do mínimo (a mesma usada no alerta de risco)."""
    return ("fraca",) if media is not None and media < NOTA_MINIMA else ()


def cor_media(media):
    """Cor do texto de uma média: vermelho se fraca, verde se ok, normal se não há média."""
    if media is None:
        return TEXTO
    return PERIGO if media < NOTA_MINIMA else BOM


def linha_nota(d):
    return (d["disciplina"], f"{d['semestre']}º", fmt(d.get("avg")), fmt(d.get("avi")),
            fmt(d.get("avc")), fmt(media_da_nota(d)))


def criar_tabela(pai, colunas, larguras=None, alinhamentos=None):
    """Cria um Treeview com barra de rolagem e devolve o Treeview.

    Por padrão a 1ª coluna fica à esquerda e as demais centralizadas; `alinhamentos` troca isso."""
    quadro = ttk.Frame(pai)
    quadro.pack(fill="both", expand=True, pady=6)
    tabela = ttk.Treeview(quadro, columns=colunas, show="headings", height=8)
    tabela.tag_configure("fraca", foreground=PERIGO)
    for i, col in enumerate(colunas):
        alinhamento = alinhamentos[i] if alinhamentos else ("w" if i == 0 else "center")
        tabela.heading(col, text=col, anchor=alinhamento)
        tabela.column(col, width=(larguras[i] if larguras else 120), anchor=alinhamento)
    barra = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
    tabela.configure(yscrollcommand=barra.set)
    tabela.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    return tabela


def preencher(tabela, linhas, iids=None, tags=None):
    """Troca o conteúdo da tabela. `iids` dá um identificador a cada linha; `tags`, as tags (cores)."""
    tabela.delete(*tabela.get_children())
    for i, linha in enumerate(linhas):
        tabela.insert("", "end", iid=iids[i] if iids else None, values=linha, tags=tags[i] if tags else ())


def texto_leitura(pai, **opcoes):
    """Caixa de texto só para leitura, no visual da interface."""
    return tk.Text(pai, wrap="word", state="disabled", relief="flat", background=CARTAO, foreground=TEXTO,
                   padx=10, pady=8, highlightthickness=1, highlightbackground=BORDA,
                   font=("Segoe UI", 10), **opcoes)


def escrever_texto(caixa, texto):
    caixa.config(state="normal")
    caixa.delete("1.0", "end")
    caixa.insert("1.0", texto)
    caixa.config(state="disabled")


def resumir(texto, limite):
    """Corta o texto no limite e deixa claro que foi cortado ("…")."""
    return texto if len(texto) <= limite else texto[:limite - 1].rstrip() + "…"


def resumo_motivos(motivos):
    """Primeiro motivo (cortado com "…" se longo) e quantos outros há: "Média geral baixa (5.8)  (+2)"."""
    if not motivos:
        return ""
    extra = f"  (+{len(motivos) - 1})" if len(motivos) > 1 else ""
    return resumir(motivos[0], 46) + extra


def limpar_campos(*entradas):
    for entrada in entradas:
        entrada.delete(0, "end")


class BarraAurora(tk.Canvas):
    """Barra de carregamento com degradê "aurora" (azul, ciano e violeta suaves) que corre em ciclo lento.

    O degradê é desenhado uma única vez, numa imagem com dois períodos, e só desliza dentro da barra.
    """

    CORES = ((47, 91, 216), (56, 178, 205), (124, 108, 224))  # azul da interface, ciano e violeta, sem neon
    PASSO_PX = 2
    INTERVALO_MS = 40  # ~50 px/s: um ciclo completo a cada ~4 s com a largura padrão

    def __init__(self, pai, largura=160, altura=8):
        super().__init__(pai, width=largura, height=altura, bd=0, highlightthickness=1,
                         highlightbackground=BORDA, background=FAIXA)
        self.largura, self.altura = largura, altura
        self.deslocamento, self.tarefa = 0, None
        self.imagem = self.gerar_degrade()  # guarda a referência, senão o Tk apaga a imagem
        self.item = self.create_image(0, 0, anchor="nw", image=self.imagem)

    def cor_em(self, x):
        """Cor do degradê na coluna x; repete a cada `largura` pixels, então o laço não tem emenda."""
        posicao = (x % self.largura) / self.largura * len(self.CORES)
        i, t = int(posicao), posicao - int(posicao)
        t = t * t * (3 - 2 * t)  # transição suave
        a, b = self.CORES[i % len(self.CORES)], self.CORES[(i + 1) % len(self.CORES)]
        return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))

    def gerar_degrade(self):
        # master explícito: sem ele o Tk usa a 1ª janela do programa (o Login, já fechada ao abrir a tela principal)
        imagem = tk.PhotoImage(master=self, width=2 * self.largura, height=self.altura)
        linhas = []
        for y in range(self.altura):
            brilho = 1.06 - 0.12 * y / max(self.altura - 1, 1)  # leve brilho no topo, sem exagero
            cores = ("#%02x%02x%02x" % tuple(min(255, round(c * brilho)) for c in self.cor_em(x))
                     for x in range(2 * self.largura))
            linhas.append("{" + " ".join(cores) + "}")
        imagem.put(" ".join(linhas))
        return imagem

    def start(self):
        if self.tarefa is None:
            self.mover()

    def mover(self):
        self.deslocamento = (self.deslocamento + self.PASSO_PX) % self.largura
        self.coords(self.item, -self.deslocamento, 0)
        self.tarefa = self.after(self.INTERVALO_MS, self.mover)

    def stop(self):
        if self.tarefa is not None:
            self.after_cancel(self.tarefa)
            self.tarefa = None


class Carregando(ttk.Frame):
    """Indicador de carregamento: barra com degradê em movimento e reticências animadas.

    Só anima enquanto `iniciar` estiver valendo e some em `parar`. Não bloqueia a janela:
    quem usa deve rodar o trabalho demorado em outra thread (veja App.rodar_em_segundo_plano).
    """

    def __init__(self, pai, texto="Carregando"):
        super().__init__(pai)
        self.texto, self.passo, self.tarefa = texto, 0, None
        self.rotulo = ttk.Label(self, anchor="w", foreground=MUDO)
        self.rotulo.pack(side="left")
        self.barra = BarraAurora(self)

    def iniciar(self, texto=None):
        if texto:
            self.texto = texto
        self.rotulo.config(width=len(self.texto) + 3)  # largura fixa: o texto não "pula" ao animar
        if self.tarefa is None:
            self.barra.pack(side="left", padx=8)
            self.barra.start()
            self.animar()

    def animar(self):
        self.rotulo.config(text=self.texto + "." * (self.passo % 4))
        self.passo += 1
        self.tarefa = self.after(350, self.animar)

    def parar(self):
        if self.tarefa is not None:
            self.after_cancel(self.tarefa)
            self.tarefa = None
        self.barra.stop()
        self.barra.pack_forget()
        self.rotulo.config(text="")


class JanelaResumo(tk.Toplevel):
    """Janela do resumo por IA: já começa a gerar, com a barra de carregamento, sem travar o programa."""

    def __init__(self, app, nome_aluno, semestres, geral):
        super().__init__(app)
        self.app, self.semestres, self.geral = app, semestres, geral
        self.em_andamento = False
        self.title(f"Resumo por IA - {nome_aluno}")
        self.geometry("620x330")
        self.minsize(480, 260)
        self.transient(app)
        self.configure(background=BG)

        corpo = ttk.Frame(self, padding=14)
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, text=f"Aluno: {nome_aluno}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(corpo, text="Só notas e disciplinas são enviadas ao Gemini; nome, matrícula, turma e "
                              "professor não.", foreground=MUDO).pack(anchor="w", pady=(2, 8))
        linha = ttk.Frame(corpo)
        linha.pack(fill="x")
        self.bt_gerar = ttk.Button(linha, text="Gerar de novo", style="Acento.TButton", command=self.gerar)
        self.bt_gerar.pack(side="left")
        self.carregando = Carregando(linha, "Gerando resumo com IA")
        self.carregando.pack(side="left", padx=12)
        self.texto = texto_leitura(corpo)
        self.texto.pack(fill="both", expand=True, pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.gerar()

    def mostrar(self, texto):
        escrever_texto(self.texto, texto)

    def gerar(self):
        if self.em_andamento:
            return
        self.em_andamento = True
        self.bt_gerar.config(state="disabled")
        self.mostrar("")
        self.carregando.iniciar()

        def terminou(texto):
            if not self.winfo_exists():  # a janela foi fechada no meio: descarta o resultado
                return
            self.em_andamento = False
            self.bt_gerar.config(state="normal")
            self.carregando.parar()
            self.mostrar(texto)

        def falhou(erro):
            terminou(str(erro) if isinstance(erro, resumo_ia.ResumoIAError) else f"Erro inesperado: {erro}")

        self.app.rodar_em_segundo_plano(
            lambda: resumo_ia.gerar_resumo(self.semestres, self.geral), terminou, falhou)

    def fechar(self):
        self.carregando.parar()
        self.destroy()


class Login(tk.Tk):
    """Tela inicial: só deixa entrar no sistema quem tem usuário e senha cadastrados."""

    def __init__(self, banco):
        super().__init__()
        self.banco = banco
        self.usuario = None
        self.perfil = None
        self.primeiro_acesso = not autenticacao.existe_admin(banco)

        self.title("Sistema de Notas Escolares - Login")
        self.minsize(380, 0)
        self.resizable(False, False)
        aplicar_tema(self)

        quadro = ttk.Frame(self, padding=28)
        quadro.pack(fill="both", expand=True)
        ttk.Label(quadro, text="Sistema de Notas Escolares",
                  font=("Segoe UI", 14, "bold")).pack(pady=(0, 4))
        subtitulo = ("Primeiro acesso: crie o administrador"
                     if self.primeiro_acesso else "Acesso restrito aos administradores")
        ttk.Label(quadro, text=subtitulo).pack(pady=(0, 16))

        ttk.Label(quadro, text="Usuário:").pack(anchor="w")
        self.e_usuario = ttk.Entry(quadro, width=34)
        self.e_usuario.pack(pady=(0, 8))
        ttk.Label(quadro, text="Senha:").pack(anchor="w")
        self.e_senha = ttk.Entry(quadro, width=34, show="*")
        self.e_senha.pack(pady=(0, 8))

        self.e_confirma = None
        self.e_codigo = None
        if self.primeiro_acesso:
            ttk.Label(quadro, text=f"Confirmar senha (mín. {autenticacao.SENHA_MINIMA}, letras e números):"
                      ).pack(anchor="w")
            self.e_confirma = ttk.Entry(quadro, width=34, show="*")
            self.e_confirma.pack(pady=(0, 8))
            if autenticacao.codigo_configuracao_exigido():
                ttk.Label(quadro, text="Código de configuração:").pack(anchor="w")
                self.e_codigo = ttk.Entry(quadro, width=34, show="*")
                self.e_codigo.pack(pady=(0, 8))

        texto = "Criar administrador" if self.primeiro_acesso else "Entrar"
        self.botao = ttk.Button(quadro, text=texto, style="Acento.TButton", command=self.confirmar)
        self.botao.pack(pady=10, fill="x")
        self.lbl_erro = ttk.Label(quadro, text="", foreground=PERIGO, wraplength=320)
        self.lbl_erro.pack()

        self.bind("<Return>", lambda e: self.confirmar())
        self.e_usuario.focus()

    def erro(self, texto):
        self.lbl_erro.config(text=texto)

    def confirmar(self):
        usuario = self.e_usuario.get().strip()
        senha = self.e_senha.get()
        if not usuario or not senha:
            return self.erro("Informe usuário e senha.")
        try:
            if self.primeiro_acesso:
                return self.criar_primeiro_admin(usuario, senha)
            documento = autenticacao.autenticar(self.banco, usuario, senha)
        except autenticacao.BloqueadoError as erro:
            minutos = -(-erro.segundos // 60)
            self.e_senha.delete(0, "end")
            return self.erro(f"Muitas tentativas inválidas. Tente de novo em {minutos} min.")
        except DuplicateKeyError:
            return self.erro("Esse usuário já existe.")
        except PyMongoError as erro:
            return messagebox.showerror("Erro no banco de dados", str(erro))

        if documento:
            self.usuario = documento["usuario"]
            self.perfil = autenticacao.perfil_do(documento)
            self.destroy()
            return
        self.e_senha.delete(0, "end")
        self.erro("Usuário ou senha incorretos.")

    def criar_primeiro_admin(self, usuario, senha):
        problema = autenticacao.validar_senha(senha)
        if problema:
            return self.erro(problema)
        if senha != self.e_confirma.get():
            return self.erro("As senhas não conferem.")
        if self.e_codigo and not autenticacao.codigo_configuracao_confere(self.e_codigo.get()):
            return self.erro("Código de configuração incorreto.")
        try:
            autenticacao.criar_primeiro_admin(self.banco, usuario, senha)
        except PermissionError as erro:
            return self.erro(str(erro))
        self.usuario = usuario.lower()
        self.perfil = autenticacao.PERFIL_ADMIN
        messagebox.showinfo("Sucesso", "Administrador criado. Você já está logado.")
        self.destroy()


class App(tk.Tk):
    def __init__(self, banco, usuario, perfil=autenticacao.PERFIL_ADMIN):
        super().__init__()
        self.banco = banco
        self.usuario = usuario
        self.perfil = perfil
        # administrador: tudo | professor: só lança notas e consulta | consulta: só visualiza
        self.eh_admin = perfil == autenticacao.PERFIL_ADMIN
        self.pode_lancar = perfil in (autenticacao.PERFIL_ADMIN, autenticacao.PERFIL_PROFESSOR)
        self.frames_abas = {}
        self.botoes_cadastro = []
        self.sair_para_login = False
        self.mapa_alunos = {}
        self.alunos_por_iid = {}
        self.disciplinas_por_iid = {}
        self.combos_alunos = []
        self.opcoes_nota = {}
        self.envio_ia_confirmado = False
        self.janela_resumo = None
        self.mapa_aloc_disc = {}
        self.mapa_professores = {}
        self.professores_por_iid = {}
        self.alocacoes_por_iid = {}
        self.lista_disciplinas = []

        self.title("Sistema de Notas Escolares")
        self.geometry("1000x720")
        aplicar_tema(self)

        barra = ttk.Frame(self, padding=(10, 6))
        barra.pack(fill="x")
        ttk.Label(barra, text=f"{perfil.capitalize()}: {usuario}").pack(side="left")
        ttk.Button(barra, text="Sair", command=self.sair).pack(side="right")

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=8, pady=8)
        self.montar_aba_alunos()
        self.montar_aba_disciplinas()
        self.montar_aba_professores()
        self.montar_aba_alocacoes()
        self.montar_aba_notas()
        self.montar_aba_boletim()
        self.montar_aba_ranking()
        self.montar_aba_risco()
        if self.eh_admin:
            self.montar_aba_usuarios()
        else:
            for botao in self.botoes_cadastro:  # cadastrar, salvar e excluir: só o administrador
                botao.config(state="disabled")
        if not self.pode_lancar:
            self.abas.hide(self.frames_abas["Lançar notas"])
        if perfil == autenticacao.PERFIL_PROFESSOR:
            for titulo, quadro in self.frames_abas.items():
                if titulo not in ABAS_DO_PROFESSOR:
                    self.abas.hide(quadro)
            self.abas.select(self.frames_abas["Lançar notas"])
        self.abas.bind("<<NotebookTabChanged>>", self.ao_trocar_aba)
        self.carregar_dados()
        if self.eh_admin:
            self.carregar_usuarios()

    def sair(self):
        """Encerra a sessão: volta para a tela de login."""
        self.sair_para_login = True
        self.destroy()

    # ---------- utilidades ----------
    def aba(self, titulo):
        quadro = ttk.Frame(self.abas, padding=12)
        self.abas.add(quadro, text=titulo)
        self.frames_abas[titulo] = quadro
        return quadro

    def exigir(self, permitido, acao):
        """Barra a ação (com aviso) se o perfil não tem permissão. Vale mesmo que o botão seja contornado."""
        if not permitido:
            messagebox.showwarning("Sem permissão", f"O perfil {self.perfil} não pode {acao}.")
        return permitido

    def campo(self, pai, rotulo, linha, largura=30):
        ttk.Label(pai, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3)
        entrada = ttk.Entry(pai, width=largura)
        entrada.grid(row=linha, column=1, sticky="w", padx=8, pady=3)
        return entrada

    def combo(self, pai, rotulo, linha, lista):
        ttk.Label(pai, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3)
        cb = ttk.Combobox(pai, state="readonly", width=40)
        cb.grid(row=linha, column=1, sticky="w", padx=8, pady=3)
        lista.append(cb)
        return cb

    def botoes_crud(self, pai, linha, rotulo_cadastrar, cadastrar, salvar, excluir, limpar):
        quadro = ttk.Frame(pai)
        quadro.grid(row=linha, column=1, sticky="w", padx=8, pady=8)
        b_cadastrar = ttk.Button(quadro, text=rotulo_cadastrar, style="Acento.TButton", command=cadastrar)
        b_salvar = ttk.Button(quadro, text="Salvar alterações", command=salvar)
        b_excluir = ttk.Button(quadro, text="Excluir", style="Perigo.TButton", command=excluir)
        b_cadastrar.pack(side="left")
        b_salvar.pack(side="left", padx=6)
        b_excluir.pack(side="left")
        ttk.Button(quadro, text="Limpar", command=limpar).pack(side="left", padx=6)
        self.botoes_cadastro += [b_cadastrar, b_salvar, b_excluir]

    def erro_banco(self, erro):
        messagebox.showerror("Erro no banco de dados", str(erro))

    def carregar_dados(self):
        """Recarrega alunos/disciplinas nas tabelas e nas caixas de seleção."""
        try:
            alunos = list(self.banco.alunos.find().sort("nome", 1))
            disciplinas = list(self.banco.disciplinas.find().sort("nome", 1))
            docentes = list(self.banco.professores.find().sort("nome", 1))
            alocacoes = professores.listar_alocacoes(self.banco)
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.mapa_alunos = {f"{a['matricula']} - {a['nome']}": a for a in alunos}
        self.alunos_por_iid = {str(a["_id"]): a for a in alunos}
        self.disciplinas_por_iid = {str(d["_id"]): d for d in disciplinas}
        for cb in self.combos_alunos:
            cb["values"] = list(self.mapa_alunos)
            if cb.get() not in self.mapa_alunos:  # aluno renomeado ou excluído
                cb.set("")
        self.lista_alunos = alunos
        self.atualizar_filtros_turma()
        self.atualizar_tabela_alunos()
        preencher(self.tab_disc, [(d["nome"], d["codigo"], d["carga_horaria"]) for d in disciplinas],
                  [str(d["_id"]) for d in disciplinas])
        self.mostrar_professores(disciplinas, docentes, alocacoes)
        self.atualizar_opcoes_disciplina()

    def ao_trocar_aba(self, _evento=None):
        aba = self.abas.tab(self.abas.select(), "text")
        if aba == "Ranking de turmas":
            self.gerar_ranking()
        elif aba == "Alerta de risco":
            self.gerar_risco()

    @staticmethod
    def selecionado(tabela, por_iid):
        """Registro da linha selecionada na tabela (ou None)."""
        escolha = tabela.selection()
        return por_iid.get(escolha[0]) if escolha else None

    # ---------- alunos ----------
    def montar_aba_alunos(self):
        f = self.aba("Alunos")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.e_nome = self.campo(form, "Nome completo:", 0)
        self.e_matricula = self.campo(form, "Matrícula:", 1)
        self.e_turma = self.campo(form, "Turma:", 2)
        self.botoes_crud(form, 3, "Cadastrar aluno", self.cadastrar_aluno,
                         self.salvar_aluno, self.excluir_aluno, self.limpar_aluno)
        self.lista_alunos = []

        filtro = ttk.Frame(f)
        filtro.pack(fill="x", pady=(8, 0))
        ttk.Label(filtro, text="Turma:").pack(side="left")
        self.cb_filtro_turma = ttk.Combobox(filtro, state="readonly", width=22, values=[TODAS_TURMAS])
        self.cb_filtro_turma.set(TODAS_TURMAS)
        self.cb_filtro_turma.pack(side="left", padx=(4, 14))
        self.cb_filtro_turma.bind("<<ComboboxSelected>>", lambda e: self.atualizar_tabela_alunos())
        ttk.Label(filtro, text="Buscar (nome ou matrícula):").pack(side="left")
        self.e_busca_aluno = ttk.Entry(filtro, width=26)
        self.e_busca_aluno.pack(side="left", padx=(4, 8))
        self.e_busca_aluno.bind("<KeyRelease>", lambda e: self.atualizar_tabela_alunos())
        ttk.Button(filtro, text="Limpar filtros", command=self.limpar_filtros_alunos).pack(side="left")
        self.lbl_contagem_alunos = ttk.Label(filtro, text="", foreground=MUDO)
        self.lbl_contagem_alunos.pack(side="right")

        ttk.Label(f, text="Alunos agrupados por turma. Selecione um aluno para editar ou excluir.",
                  foreground=MUDO).pack(anchor="w", pady=(4, 0))
        quadro = ttk.Frame(f)
        quadro.pack(fill="both", expand=True, pady=6)
        self.tab_alunos = ttk.Treeview(quadro, columns=("matricula", "turma"), show="tree headings", height=8)
        self.tab_alunos.heading("#0", text="Turma / Aluno", anchor="w")
        self.tab_alunos.column("#0", width=380, anchor="w")
        for coluna, titulo in (("matricula", "Matrícula"), ("turma", "Turma")):
            self.tab_alunos.heading(coluna, text=titulo, anchor="center")
            self.tab_alunos.column(coluna, width=150, anchor="center")
        self.tab_alunos.tag_configure("turma", background="#e3eaf7", font=("Segoe UI", 9, "bold"))
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.tab_alunos.yview)
        self.tab_alunos.configure(yscrollcommand=barra.set)
        self.tab_alunos.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tab_alunos.bind("<<TreeviewSelect>>", self.ao_selecionar_aluno)

    def atualizar_filtros_turma(self):
        """Atualiza a lista de turmas dos filtros (Alunos e Alerta de risco), mantendo a escolha."""
        turmas = sorted({a["turma"] for a in self.lista_alunos}, key=str.casefold)
        valores = [TODAS_TURMAS, *turmas]
        for cb in (self.cb_filtro_turma, self.cb_risco_turma):
            cb["values"] = valores
            if cb.get() not in valores:  # a turma escolhida deixou de existir
                cb.set(TODAS_TURMAS)
        self.cb_aloc_turma["values"] = turmas
        if self.cb_aloc_turma.get() not in turmas:
            self.cb_aloc_turma.set("")

    def atualizar_tabela_alunos(self):
        """Mostra os alunos agrupados por turma, respeitando o filtro de turma e a busca."""
        turma = self.cb_filtro_turma.get()
        busca = self.e_busca_aluno.get().strip().casefold()
        grupos = {}
        for a in self.lista_alunos:
            if turma != TODAS_TURMAS and a["turma"] != turma:
                continue
            if busca and busca not in a["nome"].casefold() and busca not in a["matricula"].casefold():
                continue
            grupos.setdefault(a["turma"], []).append(a)

        self.tab_alunos.delete(*self.tab_alunos.get_children())
        total = 0
        for nome_turma in sorted(grupos, key=str.casefold):
            alunos = sorted(grupos[nome_turma], key=lambda a: a["nome"].casefold())
            plural = "aluno" if len(alunos) == 1 else "alunos"
            pai = self.tab_alunos.insert("", "end", iid=f"turma:{nome_turma}", open=True, tags=("turma",),
                                         text=f"{nome_turma}  ({len(alunos)} {plural})", values=("", ""))
            for a in alunos:
                self.tab_alunos.insert(pai, "end", iid=str(a["_id"]), text=a["nome"],
                                       values=(a["matricula"], a["turma"]))
            total += len(alunos)
        self.lbl_contagem_alunos.config(text=f"{total} de {len(self.lista_alunos)} aluno(s)")

    def limpar_filtros_alunos(self):
        self.cb_filtro_turma.set(TODAS_TURMAS)
        self.e_busca_aluno.delete(0, "end")
        self.atualizar_tabela_alunos()

    def campos_aluno(self):
        valores = tuple(e.get().strip() for e in (self.e_nome, self.e_matricula, self.e_turma))
        if not all(valores):
            messagebox.showwarning("Atenção", "Todos os campos são obrigatórios.")
            return None
        return valores

    def ao_selecionar_aluno(self, _evento=None):
        aluno = self.selecionado(self.tab_alunos, self.alunos_por_iid)
        if aluno:
            limpar_campos(self.e_nome, self.e_matricula, self.e_turma)
            self.e_nome.insert(0, aluno["nome"])
            self.e_matricula.insert(0, aluno["matricula"])
            self.e_turma.insert(0, aluno["turma"])

    def limpar_aluno(self):
        limpar_campos(self.e_nome, self.e_matricula, self.e_turma)
        self.tab_alunos.selection_set(())

    def cadastrar_aluno(self):
        if not self.exigir(self.eh_admin, "cadastrar alunos"):
            return
        valores = self.campos_aluno()
        if not valores:
            return
        nome, mat, turma = valores
        try:
            self.banco.alunos.insert_one({"nome": nome, "matricula": mat, "turma": turma,
                                          "data_cadastro": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Essa matrícula já está cadastrada.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_aluno()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Aluno cadastrado com sucesso.")

    def salvar_aluno(self):
        if not self.exigir(self.eh_admin, "alterar alunos"):
            return
        aluno = self.selecionado(self.tab_alunos, self.alunos_por_iid)
        if not aluno:
            return messagebox.showwarning("Atenção", "Selecione um aluno na tabela.")
        valores = self.campos_aluno()
        if not valores:
            return
        nome, mat, turma = valores
        try:
            self.banco.alunos.update_one(
                {"_id": aluno["_id"]}, {"$set": {"nome": nome, "matricula": mat, "turma": turma}})
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Essa matrícula já está cadastrada.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_aluno()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Aluno atualizado.")

    def excluir_aluno(self):
        if not self.exigir(self.eh_admin, "excluir alunos"):
            return
        aluno = self.selecionado(self.tab_alunos, self.alunos_por_iid)
        if not aluno:
            return messagebox.showwarning("Atenção", "Selecione um aluno na tabela.")
        try:
            qtd = self.banco.notas.count_documents({"aluno_id": aluno["_id"]})
            if not messagebox.askyesno(
                    "Confirmar exclusão",
                    f"Excluir {aluno['nome']} e as {qtd} nota(s) dele? Isso não pode ser desfeito."):
                return
            self.banco.notas.delete_many({"aluno_id": aluno["_id"]})
            self.banco.alunos.delete_one({"_id": aluno["_id"]})
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_aluno()
        self.carregar_dados()

    # ---------- disciplinas ----------
    def montar_aba_disciplinas(self):
        f = self.aba("Disciplinas")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.e_dnome = self.campo(form, "Nome da disciplina:", 0)
        self.e_codigo = self.campo(form, "Código:", 1)
        self.e_carga = self.campo(form, "Carga horária (h):", 2, 10)
        self.botoes_crud(form, 3, "Cadastrar disciplina", self.cadastrar_disciplina,
                         self.salvar_disciplina, self.excluir_disciplina, self.limpar_disciplina)
        ttk.Label(f, text="Selecione uma linha para editar ou excluir.",
                  foreground=MUDO).pack(anchor="w")
        self.tab_disc = criar_tabela(f, ("Nome", "Código", "Carga horária"), (400, 150, 150))
        self.tab_disc.bind("<<TreeviewSelect>>", self.ao_selecionar_disciplina)

    def campos_disciplina(self):
        nome, codigo = self.e_dnome.get().strip(), self.e_codigo.get().strip()
        try:
            carga = int(self.e_carga.get().strip())
            if carga < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Atenção", "A carga horária deve ser um inteiro positivo.")
            return None
        if not nome or not codigo:
            messagebox.showwarning("Atenção", "Nome e código são obrigatórios.")
            return None
        return nome, codigo, carga

    def ao_selecionar_disciplina(self, _evento=None):
        disciplina = self.selecionado(self.tab_disc, self.disciplinas_por_iid)
        if disciplina:
            limpar_campos(self.e_dnome, self.e_codigo, self.e_carga)
            self.e_dnome.insert(0, disciplina["nome"])
            self.e_codigo.insert(0, disciplina["codigo"])
            self.e_carga.insert(0, str(disciplina["carga_horaria"]))

    def limpar_disciplina(self):
        limpar_campos(self.e_dnome, self.e_codigo, self.e_carga)
        self.tab_disc.selection_set(())

    def cadastrar_disciplina(self):
        if not self.exigir(self.eh_admin, "cadastrar disciplinas"):
            return
        valores = self.campos_disciplina()
        if not valores:
            return
        nome, codigo, carga = valores
        try:
            self.banco.disciplinas.insert_one(
                {"nome": nome, "codigo": codigo, "carga_horaria": carga})
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Esse código já está cadastrado.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_disciplina()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Disciplina cadastrada com sucesso.")

    def salvar_disciplina(self):
        if not self.exigir(self.eh_admin, "alterar disciplinas"):
            return
        disciplina = self.selecionado(self.tab_disc, self.disciplinas_por_iid)
        if not disciplina:
            return messagebox.showwarning("Atenção", "Selecione uma disciplina na tabela.")
        valores = self.campos_disciplina()
        if not valores:
            return
        nome, codigo, carga = valores
        try:
            self.banco.disciplinas.update_one(
                {"_id": disciplina["_id"]},
                {"$set": {"nome": nome, "codigo": codigo, "carga_horaria": carga}})
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Esse código já está cadastrado.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_disciplina()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Disciplina atualizada.")

    def excluir_disciplina(self):
        if not self.exigir(self.eh_admin, "excluir disciplinas"):
            return
        disciplina = self.selecionado(self.tab_disc, self.disciplinas_por_iid)
        if not disciplina:
            return messagebox.showwarning("Atenção", "Selecione uma disciplina na tabela.")
        try:
            qtd = self.banco.notas.count_documents({"disciplina_id": disciplina["_id"]})
            if not messagebox.askyesno(
                    "Confirmar exclusão",
                    f"Excluir {disciplina['nome']} e as {qtd} nota(s) lançadas nela? "
                    "Isso não pode ser desfeito."):
                return
            self.banco.notas.delete_many({"disciplina_id": disciplina["_id"]})
            professores.remover_disciplina_dos_professores(self.banco, disciplina["_id"])
            self.banco.disciplinas.delete_one({"_id": disciplina["_id"]})
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_disciplina()
        self.carregar_dados()

    # ---------- professores (o que cada um pode lecionar) ----------
    def montar_aba_professores(self):
        f = self.aba("Professores")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.e_pnome = self.campo(form, "Nome do professor:", 0)
        ttk.Label(form, text="Pode lecionar:").grid(row=1, column=0, sticky="nw", pady=3)
        self.lb_habilitadas = tk.Listbox(form, selectmode="multiple", exportselection=False, height=5,
                                         width=44, relief="flat", background=CARTAO, foreground=TEXTO,
                                         highlightthickness=1, highlightbackground=BORDA,
                                         highlightcolor=ACENTO, selectbackground=SELECAO,
                                         selectforeground=TEXTO, activestyle="none")
        self.lb_habilitadas.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        self.botoes_crud(form, 2, "Cadastrar professor", self.cadastrar_professor,
                         self.salvar_professor, self.excluir_professor, self.limpar_professor)
        ttk.Label(f, text="Marque as disciplinas que o professor pode dar. Um professor só pode ser "
                          "alocado em disciplinas marcadas aqui.", foreground=MUDO).pack(anchor="w")
        self.tab_prof = criar_tabela(f, ("Professor", "Pode lecionar"), (260, 600))
        self.tab_prof.bind("<<TreeviewSelect>>", self.ao_selecionar_professor)

    def disciplinas_marcadas(self):
        return [self.lista_disciplinas[i]["_id"] for i in self.lb_habilitadas.curselection()]

    def limpar_professor(self):
        limpar_campos(self.e_pnome)
        self.lb_habilitadas.selection_clear(0, "end")
        self.tab_prof.selection_set(())

    def ao_selecionar_professor(self, _evento=None):
        docente = self.selecionado(self.tab_prof, self.professores_por_iid)
        if not docente:
            return
        limpar_campos(self.e_pnome)
        self.e_pnome.insert(0, docente["nome"])
        self.lb_habilitadas.selection_clear(0, "end")
        for i, d in enumerate(self.lista_disciplinas):
            if d["_id"] in docente.get("disciplinas", []):
                self.lb_habilitadas.selection_set(i)

    def cadastrar_professor(self):
        if not self.exigir(self.eh_admin, "cadastrar professores"):
            return
        try:
            professores.criar_professor(self.banco, self.e_pnome.get(), self.disciplinas_marcadas())
        except professores.RegraError as erro:
            return messagebox.showwarning("Atenção", str(erro))
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Já existe um professor com esse nome.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_professor()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Professor cadastrado.")

    def salvar_professor(self):
        if not self.exigir(self.eh_admin, "alterar professores"):
            return
        docente = self.selecionado(self.tab_prof, self.professores_por_iid)
        if not docente:
            return messagebox.showwarning("Atenção", "Selecione um professor na tabela.")
        try:
            professores.atualizar_professor(self.banco, docente["_id"], self.e_pnome.get(),
                                            self.disciplinas_marcadas())
        except professores.RegraError as erro:
            return messagebox.showwarning("Atenção", str(erro))
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Já existe um professor com esse nome.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_professor()
        self.carregar_dados()
        messagebox.showinfo("Sucesso", "Professor atualizado.")

    def excluir_professor(self):
        if not self.exigir(self.eh_admin, "excluir professores"):
            return
        docente = self.selecionado(self.tab_prof, self.professores_por_iid)
        if not docente:
            return messagebox.showwarning("Atenção", "Selecione um professor na tabela.")
        if not messagebox.askyesno("Confirmar exclusão",
                                   f"Excluir {docente['nome']} e as alocações dele? Isso não pode ser desfeito."):
            return
        try:
            professores.excluir_professor(self.banco, docente["_id"])
        except professores.RegraError as erro:
            return messagebox.showwarning("Não permitido", str(erro))
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.limpar_professor()
        self.carregar_dados()

    # ---------- alocações: professor, disciplina, ano e turma ----------
    def montar_aba_alocacoes(self):
        f = self.aba("Alocações")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.cb_aloc_prof = self.combo(form, "Professor:", 0, [])
        self.cb_aloc_disc = self.combo(form, "Disciplina:", 1, [])
        ttk.Label(form, text="Ano:").grid(row=2, column=0, sticky="w", pady=3)
        self.sp_aloc_ano = ttk.Spinbox(form, from_=2000, to=2100, width=8)
        self.sp_aloc_ano.set(datetime.now().year)
        self.sp_aloc_ano.grid(row=2, column=1, sticky="w", padx=8, pady=3)
        self.cb_aloc_turma = self.combo(form, "Turma:", 3, [])
        self.cb_aloc_prof.bind("<<ComboboxSelected>>", lambda e: self.atualizar_disciplinas_alocacao())

        botoes = ttk.Frame(form)
        botoes.grid(row=4, column=1, sticky="w", padx=8, pady=8)
        b_vincular = ttk.Button(botoes, text="Vincular", style="Acento.TButton", command=self.vincular_alocacao)
        b_remover = ttk.Button(botoes, text="Remover vínculo", style="Perigo.TButton", command=self.remover_alocacao)
        b_vincular.pack(side="left")
        b_remover.pack(side="left", padx=6)
        self.botoes_cadastro += [b_vincular, b_remover]
        ttk.Label(f, text=("O mesmo professor pode ter várias turmas; a mesma turma pode ter a mesma "
                           "disciplina com professores diferentes."),
                  foreground=MUDO).pack(anchor="w")
        self.tab_aloc = criar_tabela(f, ("Professor", "Disciplina", "Ano", "Turma"), (260, 300, 80, 200))

    def mostrar_professores(self, disciplinas, docentes, alocacoes):
        """Atualiza a lista de habilitações, as tabelas e as caixas de professor/disciplina."""
        self.lista_disciplinas = disciplinas
        self.lb_habilitadas.delete(0, "end")
        for d in disciplinas:
            self.lb_habilitadas.insert("end", d["nome"])
        nomes = {d["_id"]: d["nome"] for d in disciplinas}
        self.professores_por_iid = {str(p["_id"]): p for p in docentes}
        self.mapa_professores = {p["nome"]: p for p in docentes}
        preencher(self.tab_prof,
                  [(p["nome"], ", ".join(nomes[i] for i in p.get("disciplinas", []) if i in nomes))
                   for p in docentes],
                  [str(p["_id"]) for p in docentes])
        self.alocacoes_por_iid = {str(a["_id"]): a for a in alocacoes}
        preencher(self.tab_aloc, [(a["professor"], a["disciplina"], a["ano"], a["turma"]) for a in alocacoes],
                  [str(a["_id"]) for a in alocacoes])
        self.cb_aloc_prof["values"] = list(self.mapa_professores)
        if self.cb_aloc_prof.get() not in self.mapa_professores:
            self.cb_aloc_prof.set("")
        self.atualizar_disciplinas_alocacao()

    def atualizar_disciplinas_alocacao(self):
        """Só oferece as disciplinas para as quais o professor escolhido está habilitado."""
        docente = self.mapa_professores.get(self.cb_aloc_prof.get())
        habilitadas = docente.get("disciplinas", []) if docente else []
        self.mapa_aloc_disc = {d["nome"]: d for d in self.lista_disciplinas if d["_id"] in habilitadas}
        self.cb_aloc_disc["values"] = list(self.mapa_aloc_disc)
        if self.cb_aloc_disc.get() not in self.mapa_aloc_disc:
            self.cb_aloc_disc.set("")

    def vincular_alocacao(self):
        if not self.exigir(self.eh_admin, "alocar professores"):
            return
        docente = self.mapa_professores.get(self.cb_aloc_prof.get())
        disciplina = self.mapa_aloc_disc.get(self.cb_aloc_disc.get())
        if not docente or not disciplina:
            return messagebox.showwarning("Atenção", "Selecione o professor e a disciplina.")
        try:
            ano = int(self.sp_aloc_ano.get())
        except ValueError:
            return messagebox.showwarning("Atenção", "Informe um ano válido (ex.: 2026).")
        try:
            professores.alocar(self.banco, docente["_id"], disciplina["_id"], ano, self.cb_aloc_turma.get())
        except professores.RegraError as erro:
            return messagebox.showwarning("Regra de negócio", str(erro))
        except DuplicateKeyError:
            return messagebox.showwarning("Atenção", "Esse vínculo já existe.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.carregar_dados()

    def remover_alocacao(self):
        if not self.exigir(self.eh_admin, "remover alocações"):
            return
        aloc = self.selecionado(self.tab_aloc, self.alocacoes_por_iid)
        if not aloc:
            return messagebox.showwarning("Atenção", "Selecione um vínculo na tabela.")
        try:
            professores.remover_alocacao(self.banco, aloc["_id"])
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.carregar_dados()

    # ---------- lançar notas (AVG, AVI e AVC por disciplina e semestre) ----------
    def montar_aba_notas(self):
        f = self.aba("Lançar notas")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.cb_nota_aluno = self.combo(form, "Aluno:", 0, self.combos_alunos)
        self.cb_nota_disc = self.combo(form, "Disciplina:", 1, [])  # opções dependem da turma do aluno
        ttk.Label(form, text="Semestre:").grid(row=2, column=0, sticky="w", pady=3)
        self.sp_semestre = ttk.Spinbox(form, from_=1, to=SEMESTRES, width=5, state="readonly",
                                       command=self.preencher_form_notas)
        self.sp_semestre.set(1)
        self.sp_semestre.grid(row=2, column=1, sticky="w", padx=8, pady=3)

        provas = ttk.LabelFrame(form, text="Notas das provas (0 a 10)", padding=10)
        provas.grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        self.e_provas = {}
        for i, nome in enumerate(PROVAS):
            ttk.Label(provas, text=f"{nome}:").grid(row=0, column=2 * i, padx=(0 if i == 0 else 16, 4))
            entrada = ttk.Entry(provas, width=8, justify="center")
            entrada.grid(row=0, column=2 * i + 1)
            entrada.bind("<KeyRelease>", lambda e: self.atualizar_media_previa())
            self.e_provas[nome] = entrada
        self.lbl_media_previa = ttk.Label(form, text="Média: -", font=("Segoe UI", 10, "bold"))
        self.lbl_media_previa.grid(row=4, column=1, sticky="w", padx=8)
        ttk.Button(form, text="Lançar / atualizar notas", style="Acento.TButton", command=self.lancar_nota).grid(
            row=5, column=1, sticky="w", padx=8, pady=8)

        ttk.Label(f, text="Notas do aluno selecionado:").pack(anchor="w")
        self.tab_notas = criar_tabela(f, COLUNAS_NOTAS, LARGURAS_NOTAS)
        self.cb_nota_aluno.bind("<<ComboboxSelected>>", lambda e: self.ao_mudar_aluno())
        self.cb_nota_disc.bind("<<ComboboxSelected>>", lambda e: self.ao_mudar_selecao())

    def ao_mudar_aluno(self):
        self.atualizar_opcoes_disciplina()
        self.ao_mudar_selecao()

    def atualizar_opcoes_disciplina(self):
        """Disciplinas (com o professor) que a turma do aluno selecionado pode receber."""
        aluno = self.mapa_alunos.get(self.cb_nota_aluno.get())
        try:
            opcoes = professores.opcoes_de_lancamento(self.banco, aluno["turma"]) if aluno else []
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.opcoes_nota = {rotulo: (disc, prof) for disc, prof, rotulo in opcoes}
        self.cb_nota_disc["values"] = list(self.opcoes_nota)
        if self.cb_nota_disc.get() not in self.opcoes_nota:
            self.cb_nota_disc.set("")

    def ao_mudar_selecao(self):
        self.preencher_form_notas()
        self.atualizar_notas_aluno()

    def atualizar_media_previa(self):
        valores = []
        for entrada in self.e_provas.values():
            try:
                valores.append(ler_nota_opcional(entrada.get()))
            except ValueError:
                valores.append(None)
        media = calcular_media(valores)
        self.lbl_media_previa.config(text=f"Média: {fmt(media)}", foreground=cor_media(media))

    def preencher_form_notas(self):
        """Se já existem notas para aluno + disciplina + semestre, mostra nos campos para edição."""
        for entrada in self.e_provas.values():
            entrada.delete(0, "end")
        aluno = self.mapa_alunos.get(self.cb_nota_aluno.get())
        opcao = self.opcoes_nota.get(self.cb_nota_disc.get())
        if aluno and opcao:
            try:
                existente = self.banco.notas.find_one({
                    "aluno_id": aluno["_id"], "disciplina_id": opcao[0], "professor_id": opcao[1],
                    "semestre": int(self.sp_semestre.get())})
            except PyMongoError as erro:
                return self.erro_banco(erro)
            if existente:
                for nome, entrada in self.e_provas.items():
                    valor = existente.get(nome.lower())
                    if valor is not None:
                        entrada.insert(0, f"{valor:g}")
        self.atualizar_media_previa()

    def atualizar_notas_aluno(self):
        aluno = self.mapa_alunos.get(self.cb_nota_aluno.get())
        if not aluno:
            return preencher(self.tab_notas, [])
        try:
            dados = notas_do_aluno(self.banco, aluno["_id"])
        except PyMongoError as erro:
            return self.erro_banco(erro)
        preencher(self.tab_notas, [linha_nota(d) for d in dados],
                  tags=[tag_media(media_da_nota(d)) for d in dados])

    def lancar_nota(self):
        if not self.exigir(self.pode_lancar, "lançar notas"):
            return
        aluno = self.mapa_alunos.get(self.cb_nota_aluno.get())
        opcao = self.opcoes_nota.get(self.cb_nota_disc.get())
        if not aluno or not opcao:
            return messagebox.showwarning("Atenção", "Selecione o aluno e a disciplina.")
        try:
            notas = {nome.lower(): ler_nota_opcional(e.get()) for nome, e in self.e_provas.items()}
        except ValueError:
            return messagebox.showwarning(
                "Atenção", "As notas devem ser números entre 0 e 10 (ou ficar em branco).")
        if all(v is None for v in notas.values()):
            return messagebox.showwarning("Atenção", "Informe pelo menos uma nota.")
        filtro = {"aluno_id": aluno["_id"], "disciplina_id": opcao[0], "professor_id": opcao[1],
                  "semestre": int(self.sp_semestre.get())}
        documento = {**filtro, **notas, "data_lancamento": datetime.now(timezone.utc)}
        try:
            r = self.banco.notas.replace_one(filtro, documento, upsert=True)
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.atualizar_notas_aluno()
        acao = "atualizadas" if r.matched_count else "lançadas"
        media = calcular_media(notas.values())
        extra = f" Média: {fmt(media)}." if media is not None else " A média aparece com 2 ou mais notas."
        messagebox.showinfo("Sucesso", f"Notas {acao} com sucesso.{extra}")

    # ---------- componentes compartilhados ----------
    def quadro_dados_aluno(self, pai):
        """Quadro com nome, matrícula e turma do aluno. Devolve os rótulos para preencher depois."""
        quadro = ttk.LabelFrame(pai, text="Dados do aluno", padding=10)
        quadro.pack(fill="x", pady=10)
        rotulos = {}
        for i, (chave, titulo) in enumerate((("nome", "Nome"), ("matricula", "Matrícula"), ("turma", "Turma"))):
            ttk.Label(quadro, text=f"{titulo}:", font=("Segoe UI", 9, "bold")).grid(
                row=0, column=2 * i, sticky="w", padx=(0 if i == 0 else 28, 4))
            rotulo = ttk.Label(quadro, text="-")
            rotulo.grid(row=0, column=2 * i + 1, sticky="w")
            rotulos[chave] = rotulo
        return rotulos

    @staticmethod
    def mostrar_dados_aluno(rotulos, aluno):
        for chave, rotulo in rotulos.items():
            rotulo.config(text=aluno[chave] if aluno else "-")

    # ---------- gráfico do aluno ----------
    def abrir_grafico(self):
        """Abre uma janela com o gráfico de médias por disciplina do aluno selecionado."""
        aluno = self.mapa_alunos.get(self.cb_bol_aluno.get())
        if not aluno:
            return messagebox.showwarning("Atenção", "Selecione um aluno.")
        try:
            medias = medias_por_disciplina(notas_do_aluno(self.banco, aluno["_id"]))
        except PyMongoError as erro:
            return self.erro_banco(erro)
        if not medias:
            return messagebox.showinfo("Gráfico", "Esse aluno ainda não possui médias para exibir.")
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            return messagebox.showerror(
                "Gráfico", "Instale o matplotlib (pip install matplotlib) para ver o gráfico.")
        from graficos import desenhar_medias

        janela = tk.Toplevel(self)
        janela.title(f"Médias de {aluno['nome']}")
        figura = Figure(figsize=(8, 4.5), dpi=100)
        desenhar_medias(figura, medias, aluno["nome"])
        canvas = FigureCanvasTkAgg(figura, master=janela)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ---------- boletim ----------
    def montar_aba_boletim(self):
        f = self.aba("Boletim")
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        self.cb_bol_aluno = self.combo(topo, "Aluno:", 0, self.combos_alunos)
        ttk.Button(topo, text="Ver gráfico", command=self.abrir_grafico).grid(row=0, column=2, padx=8)
        ttk.Button(topo, text="Resumo por IA", style="Acento.TButton",
                   command=self.gerar_resumo_ia).grid(row=0, column=3)
        self.lbl_bol = self.quadro_dados_aluno(f)
        self.lbl_bol_aviso = ttk.Label(f, text="Selecione um aluno para ver o boletim.", foreground=MUDO)
        self.lbl_bol_aviso.pack(anchor="w")

        # rodapé empacotado antes da tabela para nunca ficar cortado
        ttk.Label(f, text=("Média da disciplina = soma das duas maiores notas ÷ 2. "
                           "Média do semestre = média das disciplinas. "
                           "Média geral = média dos semestres.\nMédia abaixo de 6 aparece em vermelho."),
                  foreground=MUDO, justify="left").pack(side="bottom", anchor="w")
        self.lbl_media_geral = ttk.Label(f, text="Média geral: -", font=("Segoe UI", 11, "bold"))
        self.lbl_media_geral.pack(side="bottom", anchor="e", pady=(4, 2))

        quadro = ttk.Frame(f)
        quadro.pack(fill="both", expand=True, pady=6)
        self.arvore = ttk.Treeview(quadro, columns=("avg", "avi", "avc", "media"),
                                   show="tree headings", height=14)
        self.arvore.heading("#0", text="Semestre / Disciplina", anchor="w")
        self.arvore.column("#0", width=340, anchor="w")
        for coluna, titulo in (("avg", "AVG"), ("avi", "AVI"), ("avc", "AVC"), ("media", "Média")):
            self.arvore.heading(coluna, text=titulo, anchor="center")
            self.arvore.column(coluna, width=100, anchor="center")
        self.arvore.tag_configure("semestre", background=FAIXA, font=("Segoe UI", 9, "bold"))
        self.arvore.tag_configure("fraca", foreground=PERIGO)
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.cb_bol_aluno.bind("<<ComboboxSelected>>", lambda e: self.gerar_boletim())

    def rodar_em_segundo_plano(self, funcao, ao_concluir, ao_falhar):
        """Roda `funcao` numa thread, sem travar a janela, e chama o retorno na thread da tela."""
        fila = queue.Queue()

        def trabalho():
            try:
                fila.put((True, funcao()))
            except Exception as erro:  # o erro volta para a tela, que decide o que mostrar
                fila.put((False, erro))

        def verificar():
            try:
                if not self.winfo_exists():
                    return
                ok, valor = fila.get_nowait()
            except queue.Empty:
                self.after(100, verificar)
                return
            except tk.TclError:  # a janela foi fechada no meio
                return
            (ao_concluir if ok else ao_falhar)(valor)

        threading.Thread(target=trabalho, daemon=True).start()
        self.after(100, verificar)

    def gerar_resumo_ia(self):
        aluno = self.mapa_alunos.get(self.cb_bol_aluno.get())
        if not aluno:
            return messagebox.showwarning("Atenção", "Selecione um aluno.")
        try:
            semestres, geral, _ = montar_boletim(notas_do_aluno(self.banco, aluno["_id"]))
        except PyMongoError as erro:
            return self.erro_banco(erro)
        if geral is None:
            return messagebox.showinfo("Resumo por IA", "Esse aluno ainda não possui médias para resumir.")
        if not self.envio_ia_confirmado:  # pergunta uma vez por sessão, não a cada clique
            if not messagebox.askyesno(
                    "Enviar ao Gemini",
                    "As notas e os nomes das disciplinas serão enviados ao Gemini (serviço externo).\n"
                    "Nome, matrícula, turma e professor NÃO são enviados.\n\n"
                    "Continuar? (Esta pergunta aparece uma vez por sessão.)"):
                return
            self.envio_ia_confirmado = True
        if self.janela_resumo is not None and self.janela_resumo.winfo_exists():
            self.janela_resumo.fechar()
        self.janela_resumo = JanelaResumo(self, aluno["nome"], semestres, geral)

    def gerar_boletim(self):
        aluno = self.mapa_alunos.get(self.cb_bol_aluno.get())
        if not aluno:
            return messagebox.showwarning("Atenção", "Selecione um aluno.")
        try:
            dados = notas_do_aluno(self.banco, aluno["_id"])
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.mostrar_dados_aluno(self.lbl_bol, aluno)

        semestres, geral, qtd = montar_boletim(dados)
        self.arvore.delete(*self.arvore.get_children())
        for numero, disciplinas, media in semestres:
            pai = self.arvore.insert("", "end", text=f"{numero}º Semestre", open=True,
                                     values=("", "", "", fmt(media)), tags=("semestre", *tag_media(media)))
            if not disciplinas:
                self.arvore.insert(pai, "end", text="(sem notas lançadas)")
            for d in disciplinas:
                self.arvore.insert(pai, "end", text=d["disciplina"], tags=tag_media(media_da_nota(d)), values=(
                    fmt(d.get("avg")), fmt(d.get("avi")), fmt(d.get("avc")), fmt(media_da_nota(d))))

        self.lbl_media_geral.config(
            text=f"Média geral ({qtd} de {SEMESTRES} semestres com média): {fmt(geral)}",
            foreground=cor_media(geral))
        self.lbl_bol_aviso.config(text="" if dados else "Esse aluno ainda não possui notas lançadas.")

    # ---------- ranking de turmas ----------
    def montar_aba_ranking(self):
        f = self.aba("Ranking de turmas")
        self.lbl_rank_aviso = ttk.Label(f, text="", foreground=MUDO)
        self.lbl_rank_aviso.pack(anchor="w", pady=(6, 0))
        self.tab_rank = criar_tabela(f, ("Posição", "Turma", "Alunos", "Notas", "Média geral"),
                                     (80, 300, 100, 100, 130), alinhamentos=("center",) * 5)
        ttk.Label(f, text="Média da turma = média das médias (duas maiores provas) de todas as notas lançadas.",
                  foreground=MUDO).pack(anchor="w")

    def gerar_ranking(self):
        try:
            ranking = ranking_turmas(self.banco)
        except PyMongoError as erro:
            return self.erro_banco(erro)
        preencher(self.tab_rank, [(i, r["turma"], r["alunos"], r["notas"], fmt(r["media"]))
                                  for i, r in enumerate(ranking, start=1)],
                  tags=[tag_media(r["media"]) for r in ranking])
        self.lbl_rank_aviso.config(
            text="" if ranking else "Ainda não há notas com média para gerar o ranking.")


    # ---------- alerta precoce de risco ----------
    def montar_aba_risco(self):
        f = self.aba("Alerta de risco")
        topo = ttk.Frame(f)
        topo.pack(fill="x")
        ttk.Label(topo, text="Turma:").pack(side="left", padx=(0, 4))
        self.cb_risco_turma = ttk.Combobox(topo, state="readonly", width=20, values=[TODAS_TURMAS])
        self.cb_risco_turma.set(TODAS_TURMAS)
        self.cb_risco_turma.pack(side="left")
        self.cb_risco_turma.bind("<<ComboboxSelected>>", lambda e: self.mostrar_risco())
        self.lbl_risco_resumo = ttk.Label(topo, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_risco_resumo.pack(side="left", padx=14)
        self.risco_por_iid = {}
        self.risco_lista = []
        # rodapé e detalhe empacotados antes da tabela para nunca ficarem cortados
        ttk.Label(f, text=("Modelo explicável: soma pontos por média baixa, disciplinas abaixo de 6, "
                           "queda entre semestres e dados incompletos. Baixo < 25, médio 25-49, alto ≥ 50. "
                           "É um alerta para apoiar a decisão, não um veredito."),
                  foreground=MUDO, wraplength=940, justify="left").pack(side="bottom", anchor="w")
        detalhe = ttk.LabelFrame(f, text="Detalhes do alerta", padding=6)
        detalhe.pack(side="bottom", fill="x", pady=(6, 6))
        self.txt_risco = texto_leitura(detalhe, height=5)
        self.txt_risco.pack(fill="x")
        self.tab_risco = criar_tabela(
            f, ("Aluno", "Turma", "Média", "Risco", "Pontos", "Motivos"),
            (170, 80, 70, 80, 70, 470))
        self.tab_risco.column("Motivos", anchor="w")
        for nivel, cor in (("alto", "#f8d7da"), ("médio", "#fff3cd"), ("baixo", "#d9f0de")):
            self.tab_risco.tag_configure(nivel, background=cor)
        self.tab_risco.bind("<<TreeviewSelect>>", self.mostrar_detalhe_risco)
        self.mostrar_detalhe_risco()

    def mostrar_detalhe_risco(self, _evento=None):
        """Todos os motivos do aluno selecionado (a coluna da tabela mostra só o começo)."""
        r = self.selecionado(self.tab_risco, self.risco_por_iid)
        if not r:
            return escrever_texto(self.txt_risco,
                                  "Selecione um aluno na tabela para ver todos os motivos do alerta.")
        cabecalho = f"{r['nome']} ({r['turma']}): risco {r['nivel']}, {r['pontos']} ponto(s)"
        escrever_texto(self.txt_risco, cabecalho + "\n" + "\n".join(f"• {m}" for m in r["motivos"]))

    def gerar_risco(self):
        try:
            resultado = avaliar_todos(self.banco)
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.risco_lista = resultado
        self.risco_por_iid = {str(r["aluno_id"]): r for r in resultado}
        self.mostrar_risco()

    def mostrar_risco(self):
        """Preenche a tabela de risco, filtrando pela turma escolhida (a lista completa fica guardada)."""
        turma = self.cb_risco_turma.get()
        visiveis = [r for r in self.risco_lista if turma in (TODAS_TURMAS, r["turma"])]
        anterior = self.tab_risco.selection()
        self.tab_risco.delete(*self.tab_risco.get_children())
        for r in visiveis:
            self.tab_risco.insert("", "end", iid=str(r["aluno_id"]), tags=(r["nivel"],), values=(
                r["nome"], r["turma"], fmt(r["media"]), r["nivel"].capitalize(),
                r["pontos"], resumo_motivos(r["motivos"])))
        # mantém o aluno selecionado; se não havia (ou saiu do filtro), seleciona o de maior risco
        alvo = anterior[0] if anterior and self.tab_risco.exists(anterior[0]) else (
            str(visiveis[0]["aluno_id"]) if visiveis else None)
        if alvo:
            self.tab_risco.selection_set(alvo)
            self.tab_risco.see(alvo)
        self.mostrar_detalhe_risco()
        altos = sum(r["nivel"] == "alto" for r in visiveis)
        medios = sum(r["nivel"] == "médio" for r in visiveis)
        escopo = "" if turma == TODAS_TURMAS else f" ({turma})"
        self.lbl_risco_resumo.config(
            text=f"{altos} em risco alto, {medios} em risco médio, de {len(visiveis)} aluno(s){escopo}")


    # ---------- usuários (só o administrador) ----------
    def montar_aba_usuarios(self):
        f = self.aba("Usuários")
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.e_usuario_novo = self.campo(form, "Usuário:", 0)
        ttk.Label(form, text="Senha:").grid(row=1, column=0, sticky="w", pady=3)
        self.e_senha_nova = ttk.Entry(form, width=30, show="*")
        self.e_senha_nova.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        ttk.Label(form, text="Perfil:").grid(row=2, column=0, sticky="w", pady=3)
        self.cb_perfil_novo = ttk.Combobox(form, state="readonly", width=27, values=autenticacao.PERFIS_EXTRAS)
        self.cb_perfil_novo.set(autenticacao.PERFIL_PROFESSOR)
        self.cb_perfil_novo.grid(row=2, column=1, sticky="w", padx=8, pady=3)

        botoes = ttk.Frame(form)
        botoes.grid(row=3, column=1, sticky="w", padx=8, pady=8)
        self.bt_criar_usuario = ttk.Button(botoes, text="Criar usuário", style="Acento.TButton", command=self.criar_usuario)
        self.bt_criar_usuario.pack(side="left")
        ttk.Button(botoes, text="Trocar senha do selecionado",
                   command=self.trocar_senha_usuario).pack(side="left", padx=6)
        ttk.Button(botoes, text="Excluir selecionado", style="Perigo.TButton",
                   command=self.excluir_usuario).pack(side="left")
        self.lbl_limite_usuarios = ttk.Label(f, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_limite_usuarios.pack(anchor="w", pady=(4, 0))
        self.tab_usuarios = criar_tabela(f, ("Usuário", "Perfil", "Criado em"), (260, 160, 200))
        ttk.Label(f, text=("Administrador: tudo, inclusive gerenciar usuários (só existe um, e ele não pode ser "
                           "excluído).\nProfessor: só lança/edita notas e faz consultas (boletim, gráfico, resumo por IA, "
                           "ranking e alerta de risco); não vê cadastros nem usuários.\nConsulta: apenas visualiza. Para trocar a senha, escolha o usuário na "
                           "tabela e digite a nova senha no campo Senha."),
                  foreground=MUDO, justify="left").pack(anchor="w")

    def carregar_usuarios(self):
        try:
            usuarios = autenticacao.listar_usuarios(self.banco)
        except PyMongoError as erro:
            return self.erro_banco(erro)
        linhas = []
        for u in usuarios:
            criado = u.get("data_cadastro")
            linhas.append((u["usuario"], autenticacao.perfil_do(u).capitalize(),
                           criado.strftime("%d/%m/%Y %H:%M") if criado else "-"))
        preencher(self.tab_usuarios, linhas, [u["usuario"] for u in usuarios])
        extras = sum(autenticacao.perfil_do(u) in autenticacao.PERFIS_EXTRAS for u in usuarios)
        maximo = autenticacao.MAX_USUARIOS_EXTRAS
        self.lbl_limite_usuarios.config(text=f"Usuários além do administrador: {extras} de {maximo}")
        self.bt_criar_usuario.config(state="disabled" if extras >= maximo else "normal")

    def criar_usuario(self):
        if not self.exigir(self.eh_admin, "criar usuários"):
            return
        try:
            autenticacao.criar_usuario(self.banco, self.e_usuario_novo.get(), self.e_senha_nova.get(),
                                       self.cb_perfil_novo.get())
        except autenticacao.LimiteUsuariosError as erro:
            self.carregar_usuarios()
            return messagebox.showwarning("Limite de usuários", str(erro))
        except ValueError as erro:
            return messagebox.showwarning("Atenção", str(erro))
        except DuplicateKeyError:
            return messagebox.showerror("Erro", "Esse usuário já existe.")
        except PyMongoError as erro:
            return self.erro_banco(erro)
        limpar_campos(self.e_usuario_novo, self.e_senha_nova)
        self.carregar_usuarios()
        messagebox.showinfo("Sucesso", "Usuário criado.")

    def usuario_selecionado(self):
        escolha = self.tab_usuarios.selection()
        if not escolha:
            messagebox.showwarning("Atenção", "Selecione um usuário na tabela.")
            return None
        return escolha[0]

    def trocar_senha_usuario(self):
        if not self.exigir(self.eh_admin, "trocar senhas"):
            return
        nome = self.usuario_selecionado()
        if not nome:
            return
        try:
            autenticacao.trocar_senha(self.banco, nome, self.e_senha_nova.get())
        except ValueError as erro:
            return messagebox.showwarning("Atenção", str(erro))
        except PyMongoError as erro:
            return self.erro_banco(erro)
        limpar_campos(self.e_senha_nova)
        messagebox.showinfo("Sucesso", f"Senha de {nome} alterada.")

    def excluir_usuario(self):
        if not self.exigir(self.eh_admin, "excluir usuários"):
            return
        nome = self.usuario_selecionado()
        if not nome:
            return
        if not messagebox.askyesno("Confirmar exclusão", f"Excluir o usuário {nome}?"):
            return
        try:
            autenticacao.excluir_usuario(self.banco, nome)
        except PermissionError as erro:
            return messagebox.showwarning("Não permitido", str(erro))
        except PyMongoError as erro:
            return self.erro_banco(erro)
        self.carregar_usuarios()


def main():
    try:
        cliente, banco = conectar_banco()
    except (RuntimeError, PyMongoError) as erro:
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Erro de conexão", f"Não foi possível conectar ao banco '{NOME_BANCO}':\n{erro}")
        return
    try:
        while True:
            login = Login(banco)
            login.mainloop()
            if not login.usuario:
                break  # fechou a janela de login
            app = App(banco, login.usuario, login.perfil)
            app.mainloop()
            if not app.sair_para_login:
                break  # fechou a janela principal
    finally:
        cliente.close()


if __name__ == "__main__":
    main()
