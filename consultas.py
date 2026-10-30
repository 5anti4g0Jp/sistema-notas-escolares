"""Consultas simples sobre os dados cadastrados."""

from tabulate import tabulate


def listar_alunos(banco):
    """Lista todos os alunos cadastrados, ordenados por nome."""
    alunos = list(
        banco.alunos.find({}, {"nome": 1, "matricula": 1, "turma": 1}).sort("nome", 1)
    )
    linhas = [[a["nome"], a["matricula"], a["turma"]] for a in alunos]
    print(tabulate(linhas, headers=["Nome", "Matrícula", "Turma"], tablefmt="fancy_grid"))
