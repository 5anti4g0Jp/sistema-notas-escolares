"""Leitura validada de dados no terminal."""

from colorama import Fore


def ler_inteiro(mensagem, minimo=None, maximo=None):
    """Lê um inteiro do terminal, repetindo até que o valor seja válido."""
    while True:
        try:
            valor = int(input(mensagem).strip())
            if minimo is not None and valor < minimo:
                raise ValueError
            if maximo is not None and valor > maximo:
                raise ValueError
            return valor
        except ValueError:
            limite = ""
            if minimo is not None and maximo is not None:
                limite = f" entre {minimo} e {maximo}"
            print(Fore.RED + f"Digite um número inteiro válido{limite}.")
