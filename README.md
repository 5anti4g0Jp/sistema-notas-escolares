# Sistema de Notas Escolares

Python + MongoDB Atlas (banco `escola_bigdata`). Duas interfaces sobre os mesmos dados:
janelas (Tkinter) e terminal. Há também uma API REST opcional.

## Instalar em outro computador

1. **Python 3.10 ou mais novo, com Tkinter.** No Windows e no macOS ele já vem. No Linux instale o pacote
   à parte (Ubuntu/Debian: `sudo apt install python3-tk`).
2. Copie a pasta do projeto (sem `.env` nem chaves) e, dentro dela, rode `pip install -r requirements.txt`.
3. **MongoDB Atlas:** em *Network Access*, libere o IP do novo computador. Sem isso a conexão é recusada
   e o sistema mostra "Erro de conexão" ao abrir.
4. Defina `MONGODB_URI` (veja `.env.example`) e rode `python tela.py`.
5. Para só conhecer o sistema sem banco: `python demo.py` (usa dados de exemplo em memória).
6. Para conferir a instalação: `python -m unittest discover tests`.

Chaves e senhas (`MONGODB_URI`, `API_SECRET`, chaves de IA) nunca vão no código nem no ZIP: leve-as
separadamente, por um canal seguro, e defina-as como variáveis de ambiente no novo computador.

## Como executar

```
pip install -r requirements.txt
set MONGODB_URI=mongodb+srv://...      # PowerShell: $env:MONGODB_URI="..."
python tela.py      # interface gráfica
python main.py      # terminal
```

A string de conexão nunca vai no código: use a variável de ambiente `MONGODB_URI`.
Veja `.env.example`.

Opcional: defina `ADMIN_SETUP_CODE` antes do primeiro acesso para exigir um código
na criação do primeiro administrador.

## Resumo por IA (Gemini)

No Boletim, o botão **Gerar resumo** pede ao Gemini um texto curto sobre o desempenho do aluno, com uma
animação de carregamento enquanto espera (a janela continua livre). Precisa de internet e de uma chave:
defina `GEMINI_API_KEY` ou crie `chave_gemini.txt` ao lado do programa (o arquivo é ignorado pelo git).
`GEMINI_MODEL` troca o modelo. Só notas e nomes de disciplinas são enviados; nome, matrícula, turma e
professor ficam de fora, e o programa pede confirmação antes de enviar. A lógica está em `resumo_ia.py`.

## Demonstração sem banco

```
python demo.py        # dados de exemplo em memória (mongomock já está no requirements.txt)
```

## API REST (opcional)

```
pip install -r requirements.txt
python api.py --demo      # dados de exemplo em memória (precisa de mongomock)
python api.py             # banco real (precisa de MONGODB_URI)
```

Abra http://127.0.0.1:8000/docs para ver e testar as rotas. Primeiro `POST /primeiro-acesso`
(cria o administrador), depois `POST /login` (devolve o token) e use o botão **Authorize** do `/docs`.
Os perfis são administrador, professor e consulta.

## Regras
- Nota por aluno + disciplina + semestre (1 a 4), com provas AVG, AVI e AVC (0 a 10).
- Média da disciplina = soma das duas maiores notas ÷ 2 (precisa de 2 notas).
- Média do semestre = média das disciplinas; média geral = média dos semestres.
- Ranking de turmas = média das médias de todas as notas da turma.
- Alerta precoce de risco (`risco.py`): modelo explicável que soma pontos por média geral baixa
  (<7, <6, <5), disciplinas com média <6, queda ≥1 ponto entre os dois últimos semestres e dados
  incompletos. Baixo <25, médio 25-49, alto ≥50. Não é aprendizado de máquina treinado (o banco
  não guarda aprovação/reprovação).
- Professores e alocações (`professores.py`): cada professor tem uma lista de disciplinas que pode
  lecionar e só pode ser alocado (professor + disciplina + ano + turma) nelas. O mesmo professor pode
  ter várias turmas e a mesma turma pode ter a mesma disciplina com professores diferentes. A nota
  fica ligada ao professor e aparece como "Disciplina - Prof. Nome". Turmas sem alocação continuam
  lançando por disciplina, como antes.
- Senha do administrador: mínimo 8 caracteres, com letras e números.
- 5 tentativas inválidas bloqueiam o usuário por 5 minutos (registrado no banco). Na API o bloqueio vale
  por usuário + endereço de origem, então quem erra a senha do administrador de fora não o tranca para
  os outros; cada endereço também tem um limite geral de 30 erros por 5 minutos.
- Senhas guardadas com PBKDF2-HMAC-SHA256 (600 mil iterações); contas antigas são atualizadas no próximo login.
- Trocar a senha de um usuário invalida os tokens da API que ele já tinha.
- Excluir aluno ou disciplina (só na tela) apaga também as notas ligadas a ele.

## Arquivos
- `calculos.py` – regras de média, boletim e ranking (usado pelas duas interfaces)
- `autenticacao.py`, `banco.py`, `config.py` – login, conexão e índices
- `professores.py` – professores, habilitações e alocações
- `risco.py` – alerta de risco acadêmico
- `tela.py` – interface gráfica
- `main.py`, `interface.py`, `cadastros.py`, `notas.py`, `consultas.py`, `relatorios.py`, `entrada.py` – terminal
- `resumo_ia.py` – resumo do desempenho gerado pelo Gemini
- `graficos.py` – gráfico de médias
- `tests/` – testes (`python -m unittest discover tests`)

Notas antigas por bimestre (campo `nota`) não são mais lidas pelo sistema.
