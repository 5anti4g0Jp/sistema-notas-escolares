"""Alerta precoce de risco acadêmico.

Modelo estatístico explicável (não é aprendizado de máquina treinado: o banco
não guarda desfechos como aprovação/reprovação). Cada sinal soma pontos e
gera um motivo legível; a pontuação final (0 a 100) vira um nível de risco.

Sinais:
  - média geral baixa (< 7, < 6, < 5)
  - disciplinas com média abaixo de 6 na última avaliação
  - queda da média entre os dois últimos semestres com nota
  - disciplinas com dados incompletos (menos de 2 provas lançadas)
"""

from calculos import media_da_nota, montar_boletim

LIMITE_MEDIO = 25
LIMITE_ALTO = 50
NOTA_MINIMA = 6.0


def nivel_do_risco(pontos):
    if pontos >= LIMITE_ALTO:
        return "alto"
    if pontos >= LIMITE_MEDIO:
        return "médio"
    return "baixo"


def avaliar_aluno(dados):
    """Avalia as notas de um aluno (formato de calculos.notas_do_aluno).

    Devolve {"nivel", "pontos", "media", "motivos"}.
    """
    semestres, geral, _ = montar_boletim(dados)
    if geral is None:
        return {"nivel": "sem dados", "pontos": 0, "media": None,
                "motivos": ["Ainda não há médias calculáveis (são necessárias 2 provas por disciplina)."]}

    pontos, motivos = 0, []

    if geral < 5:
        pontos += 45
        motivos.append(f"Média geral muito baixa ({geral:.2f}).")
    elif geral < NOTA_MINIMA:
        pontos += 30
        motivos.append(f"Média geral abaixo de {NOTA_MINIMA:g} ({geral:.2f}).")
    elif geral < 7:
        pontos += 12
        motivos.append(f"Média geral próxima do limite ({geral:.2f}).")

    # última média de cada disciplina (semestres chegam em ordem crescente)
    ultima = {}
    for _, disciplinas, _ in semestres:
        for d in disciplinas:
            media = media_da_nota(d)
            if media is not None:
                ultima[d["disciplina"]] = media
    fracas = sorted(nome for nome, m in ultima.items() if m < NOTA_MINIMA)
    if fracas:
        pontos += min(30, 10 * len(fracas))
        motivos.append(f"Média abaixo de {NOTA_MINIMA:g} em: {', '.join(fracas)}.")

    com_media = [m for _, _, m in semestres if m is not None]
    if len(com_media) >= 2:
        queda = com_media[-2] - com_media[-1]
        if queda >= 2:
            pontos += 25
            motivos.append(f"Queda forte entre os dois últimos semestres (-{queda:.2f}).")
        elif queda >= 1:
            pontos += 15
            motivos.append(f"Queda entre os dois últimos semestres (-{queda:.2f}).")

    incompletas = {d["disciplina"] for _, discs, _ in semestres for d in discs
                   if media_da_nota(d) is None}
    if incompletas:
        pontos += min(10, 5 * len(incompletas))
        motivos.append(f"Dados incompletos em: {', '.join(sorted(incompletas))}.")

    pontos = min(100, pontos)
    if not motivos:
        motivos.append("Sem sinais de risco.")
    return {"nivel": nivel_do_risco(pontos), "pontos": pontos, "media": geral, "motivos": motivos}


def avaliar_todos(banco):
    """Avalia todos os alunos. Devolve lista (maior risco primeiro) de dicts com
    nome, matricula, turma e o resultado de avaliar_aluno."""
    pipeline = [
        {"$match": {"semestre": {"$exists": True}}},
        {"$lookup": {"from": "disciplinas", "localField": "disciplina_id",
                     "foreignField": "_id", "as": "disciplina"}},
        {"$unwind": "$disciplina"},
        {"$project": {"_id": 0, "aluno_id": 1, "disciplina": "$disciplina.nome",
                      "semestre": 1, "avg": 1, "avi": 1, "avc": 1}},
    ]
    por_aluno = {}
    for d in banco.notas.aggregate(pipeline):
        por_aluno.setdefault(d["aluno_id"], []).append(d)

    resultado = []
    for aluno in banco.alunos.find():
        avaliacao = avaliar_aluno(por_aluno.get(aluno["_id"], []))
        resultado.append({"aluno_id": aluno["_id"], "nome": aluno["nome"],
                          "matricula": aluno["matricula"],
                          "turma": aluno["turma"], **avaliacao})
    return sorted(resultado, key=lambda r: (-r["pontos"], r["nome"]))
