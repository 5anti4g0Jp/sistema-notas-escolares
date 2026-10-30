"""Regras de negócio compartilhadas pela tela e pelo terminal.

Cada nota é um documento por aluno + disciplina + semestre (+ professor), com as provas
AVG, AVI e AVC (campos "avg", "avi", "avc"; vazio = não lançada).
"""

from professores import rotulo_disciplina

SEMESTRES = 4  # curso de 2 anos = 4 semestres
PROVAS = ("AVG", "AVI", "AVC")


def ler_nota_opcional(texto):
    """Converte o texto de um campo em nota (0 a 10). Vazio vira None; inválido gera ValueError."""
    texto = texto.strip().replace(",", ".")
    if not texto:
        return None
    valor = float(texto)
    if not 0 <= valor <= 10:  # NaN também cai aqui, pois a comparação é falsa
        raise ValueError
    return round(valor, 2)


def calcular_media(valores):
    """Média do aluno: soma das duas maiores notas dividida por dois.

    Precisa de pelo menos duas notas lançadas; senão devolve None.
    """
    validos = sorted((v for v in valores if v is not None), reverse=True)
    if len(validos) < 2:
        return None
    return round((validos[0] + validos[1]) / 2, 2)


def media_da_nota(documento):
    return calcular_media([documento.get(p.lower()) for p in PROVAS])


def media_simples(valores):
    validos = [v for v in valores if v is not None]
    return round(sum(validos) / len(validos), 2) if validos else None


def fmt(valor):
    return "-" if valor is None else f"{valor:.2f}"


def notas_do_aluno(banco, aluno_id):
    """Notas do aluno (modelo por semestre) com o nome da disciplina."""
    pipeline = [
        {"$match": {"aluno_id": aluno_id, "semestre": {"$exists": True}}},
        {"$lookup": {"from": "disciplinas", "localField": "disciplina_id",
                     "foreignField": "_id", "as": "disciplina"}},
        {"$unwind": "$disciplina"},
        {"$lookup": {"from": "professores", "localField": "professor_id",
                     "foreignField": "_id", "as": "professor"}},
        {"$unwind": {"path": "$professor", "preserveNullAndEmptyArrays": True}},
        {"$project": {"_id": 0, "disciplina": "$disciplina.nome", "professor": "$professor.nome",
                      "semestre": 1, "avg": 1, "avi": 1, "avc": 1}},
    ]
    dados = list(banco.notas.aggregate(pipeline))
    for d in dados:  # disciplina concatenada com o professor (notas antigas ficam só com a disciplina)
        d["disciplina"] = rotulo_disciplina(d["disciplina"], d.pop("professor", None))
    return sorted(dados, key=lambda d: (d["disciplina"], d["semestre"]))


def montar_boletim(dados):
    """Agrupa as notas por semestre.

    Devolve (semestres, media_geral, qtd_semestres_com_media), onde semestres é
    uma lista de (numero, disciplinas, media_do_semestre) para os 4 semestres.
    Média do semestre = média das disciplinas; média geral = média dos semestres.
    """
    por_semestre = {}
    for d in dados:
        por_semestre.setdefault(d["semestre"], []).append(d)

    semestres, medias_semestres = [], []
    for numero in range(1, SEMESTRES + 1):
        disciplinas = sorted(por_semestre.get(numero, []), key=lambda d: d["disciplina"])
        media = media_simples(media_da_nota(d) for d in disciplinas)
        if media is not None:
            medias_semestres.append(media)
        semestres.append((numero, disciplinas, media))
    return semestres, media_simples(medias_semestres), len(medias_semestres)


def medias_por_disciplina(dados):
    """Média de cada disciplina ao longo dos semestres: {nome: média}."""
    por_disciplina = {}
    for d in dados:
        por_disciplina.setdefault(d["disciplina"], []).append(media_da_nota(d))
    medias = {nome: media_simples(v) for nome, v in por_disciplina.items()}
    return {nome: m for nome, m in sorted(medias.items()) if m is not None}


def ranking_turmas(banco):
    """Ranking de turmas pela média das médias das notas lançadas.

    Devolve uma lista (da melhor para a pior) de dicts com turma, media,
    alunos (com nota) e notas (registros com média calculável).
    """
    pipeline = [
        {"$match": {"semestre": {"$exists": True}}},
        {"$lookup": {"from": "alunos", "localField": "aluno_id",
                     "foreignField": "_id", "as": "aluno"}},
        {"$unwind": "$aluno"},
        {"$project": {"_id": 0, "turma": "$aluno.turma", "aluno_id": 1,
                      "avg": 1, "avi": 1, "avc": 1}},
    ]
    turmas = {}
    for d in banco.notas.aggregate(pipeline):
        media = media_da_nota(d)
        if media is None:
            continue
        turma = turmas.setdefault(d["turma"], {"medias": [], "alunos": set()})
        turma["medias"].append(media)
        turma["alunos"].add(d["aluno_id"])
    ranking = [
        {"turma": nome, "media": media_simples(t["medias"]),
         "alunos": len(t["alunos"]), "notas": len(t["medias"])}
        for nome, t in turmas.items()
    ]
    return sorted(ranking, key=lambda r: (-r["media"], r["turma"]))
