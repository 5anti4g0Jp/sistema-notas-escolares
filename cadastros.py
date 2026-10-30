"""Cadastro e seleção de alunos e disciplinas."""

from datetime import datetime, timezone

from colorama import Fore
from pymongo.errors import DuplicateKeyError

from entrada import ler_inteiro


def cadastrar_aluno(banco):
    """Cadastra um novo aluno na coleção `alunos`."""
    nome = input("Nome completo: ").strip()
    matricula = input("Matrícula: ").strip()
    turma = input("Turma: ").strip()
    if not nome or not matricula or not turma:
        print(Fore.RED + "Todos os campos são obrigatórios.")
        return

    try:
        banco.alunos.insert_one(
            {
                "nome": nome,
                "matricula": matricula,
                "turma": turma,
                "data_cadastro": datetime.now(timezone.utc),
            }
        )
        print(Fore.GREEN + "Aluno cadastrado com sucesso.")
    except DuplicateKeyError:
        print(Fore.RED + "Essa matrícula já está cadastrada.")


def cadastrar_disciplina(banco):
    """Cadastra uma nova disciplina na coleção `disciplinas`."""
    nome = input("Nome da disciplina: ").strip()
    codigo = input("Código: ").strip()
    carga_horaria = ler_inteiro("Carga horária (horas): ", 1)
    if not nome or not codigo:
        print(Fore.RED + "Nome e código são obrigatórios.")
        return

    try:
        banco.disciplinas.insert_one(
            {"nome": nome, "codigo": codigo, "carga_horaria": carga_horaria}
        )
        print(Fore.GREEN + "Disciplina cadastrada com sucesso.")
    except DuplicateKeyError:
        print(Fore.RED + "Esse código já está cadastrado.")


def selecionar_aluno(banco):
    """Busca um aluno pela matrícula, pedindo o valor ao usuário."""
    matricula = input("Matrícula do aluno: ").strip()
    aluno = banco.alunos.find_one({"matricula": matricula})
    if not aluno:
        print(Fore.RED + "Aluno não encontrado.")
    return aluno


def selecionar_disciplina(banco):
    """Busca uma disciplina pelo código, pedindo o valor ao usuário."""
    codigo = input("Código da disciplina: ").strip()
    disciplina = banco.disciplinas.find_one({"codigo": codigo})
    if not disciplina:
        print(Fore.RED + "Disciplina não encontrada.")
    return disciplina
