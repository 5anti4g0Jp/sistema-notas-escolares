"""Abre a tela com um banco de demonstração em memória (sem Atlas).

Precisa de `pip install mongomock`. Os dados somem ao fechar a janela.
Execute com: python demo.py
"""

import random

import mongomock

import banco as modulo_banco
import tela

ALUNOS = [
    ("Ana Souza", "1001", "Turma A"), ("Bruno Lima", "1002", "Turma A"),
    ("Carla Dias", "1003", "Turma B"), ("Diego Alves", "1004", "Turma B"),
    ("Elisa Rocha", "1005", "Turma C"),
    ("Fábio Nunes", "1006", "Turma C"),  # sem nenhuma nota, para testar o caso "sem dados"
]
DISCIPLINAS = [("Matemática", "MAT", 80), ("Português", "POR", 80), ("Informática", "INF", 60)]


def montar_banco():
    banco = mongomock.MongoClient()["demo"]
    modulo_banco.criar_indices(banco)
    rng = random.Random(7)
    alunos = [banco.alunos.insert_one({"nome": n, "matricula": m, "turma": t}).inserted_id
              for n, m, t in ALUNOS]
    discs = [banco.disciplinas.insert_one(
        {"nome": n, "codigo": c, "carga_horaria": h}).inserted_id for n, c, h in DISCIPLINAS]
    for i, aluno in enumerate(alunos[:-1]):  # o último aluno fica sem notas
        for disc in discs:
            for semestre in (1, 2):
                provas = [round(rng.uniform(6.5, 10), 1) for _ in range(3)]
                if i == len(alunos) - 2 and semestre == 2:  # aluna em queda, para o alerta de risco
                    provas = [round(p - 3.5, 1) for p in provas]
                provas[rng.randrange(3)] = None if rng.random() < 0.3 else provas[0]
                banco.notas.insert_one({
                    "aluno_id": aluno, "disciplina_id": disc, "semestre": semestre,
                    "avg": provas[0], "avi": provas[1], "avc": provas[2]})
    return banco



def executar(banco):
    """Mesmo fluxo da tela real: login (no 1º acesso você cria o administrador), depois o sistema.
    O botão Sair da janela principal volta ao login."""
    while True:
        login = tela.Login(banco)
        login.mainloop()
        if not login.usuario:
            break  # fechou a janela de login
        app = tela.App(banco, login.usuario, login.perfil)
        app.mainloop()
        if not app.sair_para_login:
            break  # fechou a janela principal


if __name__ == "__main__":
    executar(montar_banco())
