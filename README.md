# Sistema de Notas Escolares

Python + MongoDB Atlas (banco `escola_bigdata`). Duas interfaces sobre os mesmos dados:
janelas (Tkinter) e terminal. Há também uma API REST opcional.

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

## Demonstração sem banco

```
python demo.py        # dados de exemplo (precisa de mongomock, já listado nos testes)
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
- Senha do administrador: mínimo 8 caracteres, com letras e números.
- 5 tentativas inválidas bloqueiam o usuário por 5 minutos (registrado no banco).
- Excluir aluno ou disciplina (só na tela) apaga também as notas ligadas a ele.

## Arquivos
- `calculos.py` – regras de média, boletim e ranking (usado pelas duas interfaces)
- `autenticacao.py`, `banco.py`, `config.py` – login, conexão e índices
- `risco.py` – alerta de risco acadêmico
- `tela.py` – interface gráfica
- `main.py`, `interface.py`, `cadastros.py`, `notas.py`, `consultas.py`, `relatorios.py`, `entrada.py` – terminal
- `graficos.py` – gráfico de médias
- `tests/` – testes (`python -m unittest discover tests`)

Notas antigas por bimestre (campo `nota`) não são mais lidas pelo sistema.
