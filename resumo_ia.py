"""Resumo do desempenho do aluno gerado pelo Gemini (API REST; não precisa de biblioteca extra).

A chave vem da variável de ambiente GEMINI_API_KEY ou do arquivo `chave_gemini.txt` ao lado deste
código (o arquivo é ignorado pelo git; nunca o commite nem o coloque no ZIP).
O modelo pode ser trocado com GEMINI_MODEL.

Privacidade: só saem notas e nomes de disciplinas. Nome, matrícula, turma e nome de professor
nunca são enviados.
"""

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELO_PADRAO = "gemini-2.5-flash"
ARQUIVO_CHAVE = Path(__file__).with_name("chave_gemini.txt")
TIMEOUT_SEGUNDOS = 60
SEPARADOR_PROFESSOR = " - Prof. "


class ResumoIAError(Exception):
    """Falha ao gerar o resumo, com mensagem pronta para mostrar ao usuário."""


def obter_chave():
    chave = os.getenv("GEMINI_API_KEY", "").strip()
    if not chave and ARQUIVO_CHAVE.is_file():
        chave = ARQUIVO_CHAVE.read_text(encoding="utf-8").strip()
    if not chave:
        raise ResumoIAError("Chave do Gemini não encontrada. Defina GEMINI_API_KEY ou crie o arquivo "
                            "chave_gemini.txt ao lado do programa.")
    return chave


def montar_pedido(semestres, media_geral):
    """Texto enviado ao modelo: as notas por semestre, sem nenhum dado que identifique alguém."""
    def nota(valor):
        return "-" if valor is None else f"{valor:g}"

    linhas = []
    for numero, disciplinas, media in semestres:
        if not disciplinas:
            continue
        linhas.append(f"Semestre {numero} (média {nota(media)}):")
        for d in disciplinas:
            nome = d["disciplina"].split(SEPARADOR_PROFESSOR)[0]  # tira o professor
            linhas.append(f"  - {nome}: AVG {nota(d.get('avg'))}, AVI {nota(d.get('avi'))}, "
                          f"AVC {nota(d.get('avc'))}")
    return ("Você é um orientador pedagógico. Escreva em português, em no máximo 5 frases, um resumo "
            "do desempenho deste aluno: pontos fortes, pontos de atenção e uma sugestão prática. "
            "A média da disciplina é a soma das duas maiores notas dividida por 2. "
            "Não invente dados além dos listados.\n\n"
            f"Média geral: {nota(media_geral)}\n" + "\n".join(linhas))


def gerar_resumo(semestres, media_geral):
    """Pede o resumo ao Gemini e devolve o texto. Pode demorar: chame fora da thread da tela."""
    chave = obter_chave()
    modelo = os.getenv("GEMINI_MODEL", MODELO_PADRAO)
    corpo = json.dumps({"contents": [{"parts": [{"text": montar_pedido(semestres, media_geral)}]}]})
    pedido = urllib.request.Request(
        URL.format(modelo=modelo), data=corpo.encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": chave})  # chave fora da URL
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.load(resposta)
    except urllib.error.HTTPError as erro:
        if erro.code in (400, 401, 403):
            raise ResumoIAError("O Gemini recusou a chave ou o pedido. Confira a chave e o modelo.")
        if erro.code == 429:
            raise ResumoIAError("Limite de uso do Gemini atingido. Tente de novo em alguns minutos.")
        raise ResumoIAError(f"O Gemini respondeu com erro {erro.code}.")
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise ResumoIAError("Não foi possível falar com o Gemini (sem internet ou demorou demais).")
    except ValueError:
        raise ResumoIAError("Resposta inesperada do Gemini.")
    try:
        texto = "".join(p.get("text", "") for p in dados["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError):
        raise ResumoIAError("O Gemini não devolveu um resumo (a resposta pode ter sido bloqueada).")
    if not texto:
        raise ResumoIAError("O Gemini devolveu um resumo vazio.")
    return texto
