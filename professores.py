"""Professores, o que cada um pode lecionar e as alocações (professor + disciplina + ano + turma).

Regras de negócio:
- Um professor só pode ser alocado em disciplinas para as quais está habilitado
  (um professor de POO não dá Educação Física).
- O mesmo professor pode ter várias turmas e a mesma turma pode ter a mesma disciplina
  com professores diferentes. Só não se repete a combinação professor + disciplina + ano + turma.
"""


class RegraError(ValueError):
    """Violação de regra de negócio, com mensagem pronta para mostrar ao usuário."""


def rotulo_disciplina(nome_disciplina, nome_professor=None):
    """Disciplina concatenada com o professor: 'Matemática - Prof. Ana'."""
    return f"{nome_disciplina} - Prof. {nome_professor}" if nome_professor else nome_disciplina


def _nome_valido(nome):
    nome = (nome or "").strip()
    if not nome:
        raise RegraError("Informe o nome do professor.")
    return nome


def criar_professor(banco, nome, disciplina_ids):
    nome = _nome_valido(nome)
    if not disciplina_ids:
        raise RegraError("Marque pelo menos uma disciplina que o professor pode lecionar.")
    return banco.professores.insert_one({"nome": nome, "nome_chave": nome.casefold(),
                                         "disciplinas": list(disciplina_ids)}).inserted_id


def atualizar_professor(banco, professor_id, nome, disciplina_ids):
    """Renomeia e/ou troca as disciplinas habilitadas.

    Não deixa tirar uma habilitação que já está em uso numa alocação.
    """
    nome = _nome_valido(nome)
    if not disciplina_ids:
        raise RegraError("Marque pelo menos uma disciplina que o professor pode lecionar.")
    em_uso = banco.alocacoes.distinct(
        "disciplina_id", {"professor_id": professor_id, "disciplina_id": {"$nin": list(disciplina_ids)}})
    if em_uso:
        nomes = ", ".join(d["nome"] for d in banco.disciplinas.find({"_id": {"$in": em_uso}}))
        raise RegraError(f"Não dá para tirar {nomes}: o professor já está alocado nela(s). "
                         "Remova a alocação primeiro.")
    banco.professores.update_one({"_id": professor_id},
                                 {"$set": {"nome": nome, "nome_chave": nome.casefold(),
                                           "disciplinas": list(disciplina_ids)}})


def excluir_professor(banco, professor_id):
    """Exclui o professor e as alocações dele. Recusa se ele já lançou notas."""
    notas = banco.notas.count_documents({"professor_id": professor_id})
    if notas:
        raise RegraError(f"O professor lançou {notas} nota(s) e não pode ser excluído.")
    banco.alocacoes.delete_many({"professor_id": professor_id})
    banco.professores.delete_one({"_id": professor_id})


def alocar(banco, professor_id, disciplina_id, ano, turma):
    """Vincula professor a disciplina + ano + turma, respeitando a habilitação do professor."""
    turma = (turma or "").strip()
    if not turma:
        raise RegraError("Informe a turma.")
    if not isinstance(ano, int) or not 2000 <= ano <= 2100:
        raise RegraError("Informe um ano válido (ex.: 2026).")
    professor = banco.professores.find_one({"_id": professor_id})
    disciplina = banco.disciplinas.find_one({"_id": disciplina_id})
    if not professor or not disciplina:
        raise RegraError("Selecione o professor e a disciplina.")
    if disciplina_id not in professor.get("disciplinas", []):
        raise RegraError(f"{professor['nome']} não está habilitado(a) para lecionar {disciplina['nome']}.")
    return banco.alocacoes.insert_one({  # DuplicateKeyError se o vínculo já existe
        "professor_id": professor_id, "disciplina_id": disciplina_id, "ano": ano, "turma": turma,
    }).inserted_id


def remover_alocacao(banco, alocacao_id):
    """Remove o vínculo. As notas já lançadas continuam, ligadas ao professor."""
    banco.alocacoes.delete_one({"_id": alocacao_id})


def remover_disciplina_dos_professores(banco, disciplina_id):
    """Ao excluir uma disciplina, tira a habilitação e as alocações dela."""
    banco.alocacoes.delete_many({"disciplina_id": disciplina_id})
    banco.professores.update_many({}, {"$pull": {"disciplinas": disciplina_id}})


def listar_alocacoes(banco, turma=None):
    """Alocações com nomes, ordenadas por professor, disciplina, ano e turma.

    Com `turma`, consulta só ela. Vínculos cujo professor ou disciplina não existem mais são ignorados.
    """
    alocacoes = list(banco.alocacoes.find({"turma": turma} if turma else {}))
    professores = {p["_id"]: p["nome"] for p in banco.professores.find(
        {"_id": {"$in": [a["professor_id"] for a in alocacoes]}})}
    disciplinas = {d["_id"]: d["nome"] for d in banco.disciplinas.find(
        {"_id": {"$in": [a["disciplina_id"] for a in alocacoes]}})}
    linhas = [{"_id": a["_id"], "professor_id": a["professor_id"], "disciplina_id": a["disciplina_id"],
               "professor": professores[a["professor_id"]], "disciplina": disciplinas[a["disciplina_id"]],
               "ano": a["ano"], "turma": a["turma"]}
              for a in alocacoes if a["professor_id"] in professores and a["disciplina_id"] in disciplinas]
    return sorted(linhas, key=lambda a: (a["professor"].casefold(), a["disciplina"].casefold(),
                                         a["ano"], a["turma"].casefold()))


def opcoes_de_lancamento(banco, turma):
    """O que pode receber notas de alunos da turma: [(disciplina_id, professor_id, rótulo)].

    Se a turma tem alocações, só elas valem (disciplina + professor). Turmas sem nenhuma
    alocação continuam lançando por disciplina, como antes dos professores existirem.
    """
    alocacoes = listar_alocacoes(banco, turma)
    if alocacoes:
        vistos, opcoes = set(), []
        for a in alocacoes:  # o mesmo vínculo em anos diferentes vira uma só opção
            chave = (a["disciplina_id"], a["professor_id"])
            if chave not in vistos:
                vistos.add(chave)
                opcoes.append((a["disciplina_id"], a["professor_id"],
                               rotulo_disciplina(a["disciplina"], a["professor"])))
        return opcoes
    return [(d["_id"], None, f"{d['codigo']} - {d['nome']}")
            for d in banco.disciplinas.find().sort("nome", 1)]


def candidatos(banco, turma, disciplina_id):
    """Professores que podem lançar nota nessa disciplina para a turma: [(professor_id, nome)].

    Turma sem alocações: [(None, None)] (lançamento só por disciplina). Lista vazia = a turma não tem a disciplina.
    """
    alocacoes = listar_alocacoes(banco, turma)
    if not alocacoes:
        return [(None, None)] if banco.disciplinas.find_one({"_id": disciplina_id}) else []
    return list({a["professor_id"]: a["professor"] for a in alocacoes
                 if a["disciplina_id"] == disciplina_id}.items())


def resolver_professor(banco, turma, disciplina_id, professor_id=None):
    """Professor dono da nota, ou RegraError. É a regra única usada pela tela, pelo terminal e pela API."""
    validos = candidatos(banco, turma, disciplina_id)
    if not validos:
        raise RegraError("Essa disciplina não é lecionada na turma do aluno.")
    if professor_id is not None:
        if professor_id in [p for p, _ in validos]:
            return professor_id
        raise RegraError("Esse professor não leciona essa disciplina nessa turma.")
    if len(validos) == 1:
        return validos[0][0]
    raise RegraError("Mais de um professor leciona essa disciplina na turma: informe o professor.")
