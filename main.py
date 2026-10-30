"""Versão de terminal do sistema de notas escolares. Execute com: python main.py

A variável de ambiente MONGODB_URI precisa estar definida. Para a versão
com janelas, execute `python tela.py`.
"""

from colorama import Fore, init
from pymongo.errors import PyMongoError

from banco import conectar_banco
from config import NOME_BANCO
from interface import fazer_login, menu


def main():
    init(autoreset=True)
    try:
        cliente, banco = conectar_banco()
    except (RuntimeError, PyMongoError) as erro:
        print(Fore.RED + f"Não foi possível conectar ao banco '{NOME_BANCO}': {erro}")
        return
    try:
        acesso = fazer_login(banco)  # (usuário, perfil) ou None
        if acesso:
            menu(banco, *acesso)
    except PyMongoError as erro:
        print(Fore.RED + f"Erro no banco de dados: {erro}")
    except (KeyboardInterrupt, EOFError):
        print("\nEncerrado.")
    finally:
        cliente.close()


if __name__ == "__main__":
    main()
