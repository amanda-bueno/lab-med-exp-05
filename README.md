# Laboratorio 05 - GraphQL vs REST

Implementacao reproduzivel do experimento controlado proposto no plano do Laboratorio 05.

O projeto compara REST e GraphQL usando o mesmo banco SQLite, a mesma camada de servicos e os mesmos cenarios de consulta. A coleta mede, no cliente, o tempo total de resposta e o tamanho do corpo recebido em bytes.

## Estrutura

```text
api/
  server.py
  internal/
    database.py
    services.py
experiment/
  config.py
  scenarios.py
  run_experiment.py
analysis/
  statistical_analysis.py
dashboard/
  app.py
  web/index.html
data/
  .gitkeep
```

## Requisitos

- Python 3.10 ou superior.
- Bibliotecas para analise estatistica: `pandas`, `numpy` e `scipy`.

O servidor e o coletor usam apenas a biblioteca padrao do Python.

Instale as dependencias de analise com:

```powershell
python -m pip install -r requirements.txt
```

## 1. Iniciar a API

```powershell
python -m api.server
```

Na primeira execucao, o banco `data/lab05.sqlite` sera criado e populado por padrao com:

- 1.000 usuarios;
- 10.000 postagens;
- 50.000 comentarios.

Para usar uma base menor durante testes:

```powershell
$env:LAB05_USERS=100
$env:LAB05_POSTS=1000
$env:LAB05_COMMENTS=5000
python -m api.server
```

Endpoints principais:

- REST: `http://127.0.0.1:8000/users/100`
- GraphQL: `http://127.0.0.1:8000/graphql`

## 2. Executar a coleta

Em outro terminal:

```powershell
python -m experiment.run_experiment
```

Configuracoes padrao:

- 10 execucoes de aquecimento por cenario e tecnologia;
- 100 repeticoes validas por cenario;
- 5 cenarios;
- 1.000 linhas validas em `data/raw_results.csv`.

Para uma execucao curta de verificacao:

```powershell
$env:LAB05_WARMUP=1
$env:LAB05_REPETITIONS=2
python -m experiment.run_experiment
```

## 3. Rodar a analise estatistica

```powershell
python -m analysis.statistical_analysis
```

Saidas:

- `data/processed_results.csv`: estatisticas descritivas por cenario, tratamento e metrica;
- `data/statistical_results.csv`: teste pareado, p-valor corrigido por Holm, tamanho de efeito e diferenca percentual.

## 4. Abrir o dashboard

```powershell
python dashboard/app.py
```

Depois acesse:

```text
http://127.0.0.1:8050/dashboard/web/index.html
```

O dashboard possui quatro abas:

- Visao Geral;
- RQ1: Tempo de Resposta;
- RQ2: Tamanho da Resposta;
- Analise Estatistica.

## Cenarios implementados

| Cenario | REST | GraphQL |
| --- | --- | --- |
| `simple_user` | `GET /users/100` | `user(id: 100) { id name email }` |
| `user_list` | `GET /users?page=1&limit=50` | `users(page: 1, limit: 50) { id name city }` |
| `nested_data` | usuario, postagens e comentarios em multiplas chamadas | usuario, postagens e comentarios em uma consulta |
| `post_titles` | busca postagens do usuario e mede o corpo completo | busca somente `title` |
| `full_profile` | usuario, postagens e comentarios completos em multiplas chamadas | dados completos equivalentes em uma consulta |

Nos cenarios REST com multiplas chamadas, o tempo e o tamanho sao acumulados ate completar a tarefa experimental, como exigido no plano.

## Hipoteses

- RQ1: consultas GraphQL apresentam menor tempo de resposta que consultas REST?
- RQ2: consultas GraphQL apresentam respostas com tamanho menor que consultas REST?

As hipoteses nulas assumem ausencia de diferenca estatisticamente significativa entre REST e GraphQL. O script de analise calcula diferencas pareadas `REST - GraphQL`, aplica Shapiro-Wilk, escolhe teste t pareado ou Wilcoxon, corrige p-valores com Holm e calcula tamanho de efeito.
