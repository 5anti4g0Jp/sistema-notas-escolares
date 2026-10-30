"""Lançamento e atualização de notas dos alunos (AVG, AVI e AVC por semestre)."""

from datetime import datetime, timezone

from colorama import Fore

from cadastros import selecionar_aluno, selecionar_disciplina
from calculos import PROVAS, SEMESTRES, calcular_media, fmt, ler_nota_opcional
from entrada import ler_inteiro


def ler_prova(nome, atual):
    """Pergunta uma prova. Enter mantém o valor atual; '-' apaga a nota."""
    dica = f"atual: {atual:g}, Enter mantém, - apaga" if atual is not None else "Enter deixa em branco"
    while True:
        texto = input(f"{nome} (0 a 10; {dica}): ").strip()
        if not texto:
            return atual
        if texto == "-":
            return None
        try:
            return ler_nota_opcional(texto)
        except ValueError:
            print(Fore.RED + "A nota deve ser um número entre 0 e 10.")


def lancar_nota(banco):
    """Lança ou atualiza (upsert) as notas de um aluno em uma disciplina/semestre."""
    aluno = selecionar_aluno(banco)
    if not aluno:
        return
    disciplina = selecionar_disciplina(banco)
    if not disciplina:
        return

    semestre = ler_inteiro(f"Semestre (1 a {SEMESTRES}): ", 1, SEMESTRES)
    filtro = {"aluno_id": aluno["_id"], "disciplina_id": disciplina["_id"], "semestre": semestre}
    existente = banco.notas.find_one(filtro) or {}

    notas = {nome.lower(): ler_prova(nome, existente.get(nome.lower())) for nome in PROVAS}
    if all(v is None for v in notas.values()):
        print(Fore.YELLOW + "Nenhuma nota informada; nada foi salvo.")
        return

    documento = {**filtro, **notas, "data_lancamento": datetime.now(timezone.utc)}
    resultado = banco.notas.replace_one(filtro, documento, upsert=True)
    acao = "atualizadas" if resultado.matched_count else "lançadas"
    media = calcular_media(notas.values())
    extra = f" Média: {fmt(media)}." if media is not None else " A média aparece com 2 ou mais notas."
    print(Fore.GREEN + f"Notas {acao} com sucesso.{extra}")
