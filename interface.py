"""Login e menu do sistema no terminal."""

from getpass import getpass

from colorama import Fore
from pymongo.errors import DuplicateKeyError

import autenticacao
from cadastros import cadastrar_aluno, cadastrar_disciplina
from consultas import listar_alunos
from notas import lancar_nota
from relatorios import (gerar_alerta_risco, gerar_ranking_turmas,
                        gerar_relatorio_aluno)

MAX_TENTATIVAS = 3


def criar_primeiro_admin(banco):
    """Primeiro acesso: cadastra o administrador. Devolve o usuário ou None."""
    print(Fore.CYAN + "Primeiro acesso: crie o administrador.")
    if autenticacao.codigo_configuracao_exigido():
        if not autenticacao.codigo_configuracao_confere(getpass("Código de configuração: ")):
            print(Fore.RED + "Código de configuração incorreto.")
            return None
    usuario = input("Usuário: ").strip()
    senha = getpass("Senha: ")
    if not usuario:
        print(Fore.RED + "Informe o usuário.")
        return None
    erro = autenticacao.validar_senha(senha)
    if erro:
        print(Fore.RED + erro)
        return None
    if senha != getpass("Confirmar senha: "):
        print(Fore.RED + "As senhas não conferem.")
        return None
    try:
        autenticacao.criar_primeiro_admin(banco, usuario, senha)
    except (DuplicateKeyError, PermissionError) as erro_cadastro:
        print(Fore.RED + (str(erro_cadastro) if isinstance(erro_cadastro, PermissionError)
                          else "Esse usuário já existe."))
        return None
    print(Fore.GREEN + "Administrador criado.")
    return usuario.lower()


def fazer_login(banco):
    """Pede usuário e senha. Devolve (usuário, perfil) ou None."""
    if not autenticacao.existe_admin(banco):
        usuario = criar_primeiro_admin(banco)
        return (usuario, autenticacao.PERFIL_ADMIN) if usuario else None
    print(Fore.CYAN + "Acesso restrito a usuários cadastrados.")
    for _ in range(MAX_TENTATIVAS):
        usuario = input("Usuário: ").strip()
        senha = getpass("Senha: ")
        try:
            documento = autenticacao.autenticar(banco, usuario, senha)
        except autenticacao.BloqueadoError as erro:
            minutos = -(-erro.segundos // 60)
            print(Fore.RED + f"Muitas tentativas. Tente novamente em {minutos} min.")
            return None
        if documento:
            return documento["usuario"], autenticacao.perfil_do(documento)
        print(Fore.RED + "Usuário ou senha incorretos.")
    return None


# Quem pode usar cada opção do menu (as demais valem para todos os perfis).
_ADMIN = (autenticacao.PERFIL_ADMIN,)
_ADMIN_E_PROFESSOR = (autenticacao.PERFIL_ADMIN, autenticacao.PERFIL_PROFESSOR)
PERMISSOES = {"1": _ADMIN, "2": _ADMIN, "3": _ADMIN_E_PROFESSOR}
OPCOES = (
    ("1", "Cadastrar aluno"), ("2", "Cadastrar disciplina"), ("3", "Lançar ou editar notas"),
    ("4", "Listar alunos"), ("5", "Relatório de aluno"), ("6", "Ranking de turmas"),
    ("7", "Alerta de risco acadêmico"),
)


def opcao_permitida(opcao, perfil):
    return perfil in PERMISSOES.get(opcao, autenticacao.PERFIS_EXTRAS + _ADMIN)


def menu(banco, usuario, perfil=autenticacao.PERFIL_ADMIN):
    """Loop principal do menu de opções do sistema (só mostra o que o perfil pode usar)."""
    while True:
        print(Fore.CYAN + f"\n=== SISTEMA DE NOTAS === ({perfil}: {usuario})")
        for codigo, texto in OPCOES:
            if opcao_permitida(codigo, perfil):
                print(f"{codigo} - {texto}")
        print("0 - Sair")
        opcao = input("Escolha uma opção: ").strip()

        if opcao in PERMISSOES and not opcao_permitida(opcao, perfil):
            print(Fore.RED + f"O perfil {perfil} não pode usar esta opção.")
        elif opcao == "1":
            cadastrar_aluno(banco)
        elif opcao == "2":
            cadastrar_disciplina(banco)
        elif opcao == "3":
            lancar_nota(banco)
        elif opcao == "4":
            listar_alunos(banco)
        elif opcao == "5":
            gerar_relatorio_aluno(banco)
        elif opcao == "6":
            gerar_ranking_turmas(banco)
        elif opcao == "7":
            gerar_alerta_risco(banco)
        elif opcao == "0":
            print("Até mais!")
            break
        else:
            print(Fore.RED + "Opção inválida.")
