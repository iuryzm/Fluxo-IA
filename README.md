# 🤖 Fluxo IA — Mapear · Extrair · Aplicar

Um trio de scripts em **Python puro (zero dependências externas)** para editar
projetos grandes com a ajuda de uma IA de chat, gastando o **mínimo de contexto/tokens**
possível.

## O problema que isto resolve

Colar um projeto inteiro no chat da IA estoura a janela de contexto, é caro e
confunde o modelo. Mas a IA também não consegue editar bem código que não viu.

Este fluxo resolve isso em três etapas, sempre conversando com a IA por **nome**
de função/classe (via [AST](https://docs.python.org/3/library/ast.html)), nunca
por número de linha:

1. **Mapear** — você manda só um *resumo* da arquitetura (assinaturas, docstrings, imports).
2. **Extrair** — a IA pede apenas os trechos que precisa ver, e você manda só eles.
3. **Aplicar** — a IA devolve o código novo de cada função/classe, e o script localiza
   o alvo pelo nome e faz a substituição automaticamente.

A IA nunca precisa lidar com posições de linha, indentação ou diffs.

## Os três scripts

| Script | Papel | Entrada | Saída |
|---|---|---|---|
| `mapear.py` | Gera o mapear da arquitetura do projeto | `.gitignore` do projeto | `.md` (mapear + instruções p/ IA) |
| `extrator.py` | Extrai os trechos de código que a IA pediu | resposta JSON da IA | `.md` (código-fonte solicitado) |
| `aplicador.py` | Aplica as mudanças que a IA propôs | resposta da IA (plano + código) | arquivos editados / patch Git |

## Requisitos

- **Python 3.9+** (usa `ast.unparse`, `ast.get_source_segment` e `end_lineno`).
- Nenhuma biblioteca externa — só a standard library (`ast`, `re`, `json`,
  `argparse`, `pathlib`, `difflib`, `shutil`, `fnmatch`).

Não há nada para instalar. Basta ter os três `.py` numa pasta.

---

## O fluxo completo, passo a passo

```
┌─────────────┐   mapear.md    ┌─────────┐  JSON do que   ┌────────────┐
│ mapear  │ ───────────▶ │   VOCÊ  │ ── precisa ──▶ │ extrator   │
└─────────────┘              │  +  IA  │                └────────────┘
                             │  (chat) │                       │
┌─────────────┐  arquivos    │         │  código + plano       │ codigo_para_ia.md
│ aplicador   │ ◀─ editados ─│         │ ◀─────────────────────┘
└─────────────┘              └─────────┘
```

### 1. Gerar o mapear do projeto

```bash
python mapear.py ../MeuProjeto/.gitignore ./test/mapear.md
```

Cole o conteúdo de `mapear.md` no chat da IA **junto com a sua tarefa**
("implemente X", "corrija o bug Y"...). O mapear já inclui, no fim, as instruções
para a IA responder no formato certo.

### 2. Extrair o código que a IA pediu

A IA vai responder com um bloco ```` ```json ```` dizendo quais arquivos,
classes ou funções ela precisa ver. Salve essa resposta num arquivo (ex.
`resposta.json`) e rode:

```bash
python extrator.py ./test/resposta.json ../MeuProjeto ./test/codigo_para_ia.md
```

Cole `codigo_para_ia.md` de volta no chat. Por padrão, esse arquivo **já termina
com as instruções de formato do `aplicador.py`** — então a IA recebe o código e,
no mesmo lugar, o guia de como devolver a solução. Não é preciso rodar
`aplicador.py --instrucoes` à parte.

### 3. Aplicar a solução

Agora com o código em mãos, a IA devolve um **plano** (JSON) + um **bloco de
código por operação**. Salve essa resposta (ex. `solucao.md`) e:

```bash
# (recomendado) ver o que mudaria, sem gravar nada:
python aplicador.py ./test/solucao.md ../MeuProjeto

# gravar de verdade (cria backups .bak por padrão):
python aplicador.py ./test/solucao.md ../MeuProjeto --aplicar
```

---

## Detalhes de cada script

### `mapear.py`

Lê o `.gitignore` do projeto-alvo e usa as linhas de **negação** (que começam
com `!`) como a *lista de inclusão* do mapear. Ou seja: os arquivos que você
"des-ignorou" no `.gitignore` são exatamente os que entram no resumo.

Para cada arquivo `.py`, extrai via AST: classes (com herança e docstring),
funções/métodos (com argumentos, tipo de retorno e docstring) e os imports.
Arquivos não-Python (configs) entram numa seção própria, apenas listados com
uma prévia das primeiras linhas (binários têm o conteúdo omitido). Por fim,
acrescenta as seções `[Unreleased]` e `[WorkingAt]` do `CHANGELOG.md`, se existir.

**Argumentos:**

| Argumento | Descrição |
|---|---|
| `gitignore_path` | Caminho do `.gitignore` do projeto-alvo (posicional). |
| `output_path` | Caminho do `.md` de saída (posicional). |
| `--linhas-config N` | Nº de linhas de prévia dos arquivos de config (padrão 20; `0` = sem prévia). |
| `--excluir PADRÃO ...` | Padrões glob a ignorar no resumo (ex.: `*.env "src/segredo.py"`). |

Você também pode criar um arquivo `.resumoignore` na raiz do projeto (um padrão
glob por linha, `#` para comentários) — ele soma com o `--excluir`.

```bash
python mapear.py ../MeuProjeto/.gitignore ./test/mapear.md --linhas-config 10 --excluir *.env README.md "scripts/*"
```

### `extrator.py`

Lê o JSON da resposta da IA e extrai exatamente o que foi pedido, usando AST
para recortar classes e funções individuais (sem precisar mandar o arquivo
inteiro).

**Formato do JSON esperado:**

```json
{
  "arquivos_completos": [
    "caminho/relativo/arquivo1.py",
    "caminho/relativo/config.yaml"
  ],
  "classes": {
    "caminho/relativo/arquivo2.py": ["NomeDaClasse", "OutraClasse"]
  },
  "funcoes": {
    "caminho/relativo/arquivo3.py": ["nome_da_funcao", "outra_funcao"]
  }
}
```

Configs (`.json`, `.yaml`, etc.) só podem vir por `arquivos_completos` — não dá
para pedir "classe" ou "função" de um arquivo não-Python.

Ao fim da saída, o `extrator.py` anexa automaticamente as instruções de formato
do `aplicador.py` (o guia de plano + blocos de código). Para isso funcionar, o
`aplicador.py` precisa estar **na mesma pasta** que o `extrator.py`; se não
estiver, a extração continua normalmente, apenas sem o anexo (com um aviso).

**Argumentos:**

| Argumento | Descrição |
|---|---|
| `resposta_ia` | Arquivo com a resposta JSON da IA (posicional). |
| `diretorio_projeto` | Raiz do projeto-alvo (posicional). |
| `output_path` | Caminho do `.md` de saída (posicional). |
| `--sem-instrucoes` | Não anexa o guia do `aplicador.py` ao fim — gera só o código puro. |

```bash
python extrator.py ./test/resposta.json ../MeuProjeto ./test/codigo_para_ia.md

# só o código, sem o guia de aplicação no fim:
python extrator.py ./test/resposta.json ../MeuProjeto ./test/codigo_para_ia.md --sem-instrucoes
```

### `aplicador.py`

Aplica as mudanças localizando cada alvo pelo **nome** (via AST) e substituindo
o nó correspondente. Re-indenta o código automaticamente, então a IA não precisa
se preocupar com colunas nem com a posição no arquivo.

**Formato da resposta da IA** — duas partes:

1. Um plano em bloco de **quatro** crases ```` ````json ````:

```json
{
  "operacoes": [
    {"acao": "substituir", "arquivo": "src/core.py", "tipo": "funcao", "alvo": "processa",   "codigo_id": "b1"},
    {"acao": "substituir", "arquivo": "src/core.py", "tipo": "metodo", "alvo": "Motor.run",  "codigo_id": "b2"},
    {"acao": "adicionar",  "arquivo": "src/core.py", "tipo": "metodo", "alvo": "Motor.reset", "codigo_id": "b3"},
    {"acao": "arquivo",    "arquivo": "config.yaml", "codigo_id": "b4"}
  ]
}
```

2. Um bloco de código por operação, com `id=` igual ao `codigo_id` do plano:

````text
````python id=b1
def processa(self, dados):
    return dados * 2
````
````

**Regras das operações:**

- `acao`: `substituir` (nó existente), `adicionar` (nó novo) ou `arquivo`
  (substitui/cria o arquivo inteiro — use para configs e arquivos novos).
- `tipo`: `funcao`, `classe` ou `metodo`. Para `metodo`, o `alvo` deve ser
  `"NomeDaClasse.nome_do_metodo"`.
- `adicionar` com tipo `metodo` insere o método no fim da classe; com `funcao`/`classe`,
  insere no nível do módulo.

**Argumentos:**

| Argumento | Descrição |
|---|---|
| `resposta_ia` | Arquivo com a resposta da IA (plano + blocos). |
| `diretorio_projeto` | Raiz do projeto-alvo. |
| `--aplicar` | Grava as mudanças (sem isso, é **dry-run**). |
| `--diff CAMINHO` | Salva um patch unificado combinado (aplicável com `git apply`). |
| `--sem-backup` | Não cria arquivos `.bak`. |
| `--instrucoes` | Imprime as instruções para colar no chat com a IA e sai. |

```bash
# imprimir as instruções para a IA:
python aplicador.py --instrucoes

# salvar um patch para revisar/aplicar com Git:
python aplicador.py ./test/solucao.md ../MeuProjeto --diff ./test/mudancas.patch
git apply --check ./test/mudancas.patch
git apply ./test/mudancas.patch
```

---

## Segurança e garantias

- **Dry-run por padrão:** o `aplicador.py` só grava com `--aplicar`.
- **Backups automáticos:** cada arquivo alterado vira um `.bak` (desative com `--sem-backup`).
- **Guarda-corpo de sintaxe:** se o resultado de um `.py` não fizer *parse*, o
  arquivo **não** é alterado.
- **Patch Git:** com `--diff`, você revisa as mudanças como um diff antes de aplicar.

## Limitações conhecidas

- Funciona com funções/classes no nível do módulo e métodos a um nível de
  profundidade (`Classe.metodo`). Classes aninhadas e funções internas mais
  profundas não são alvos válidos.
- O arquivo `.py` precisa estar sintaticamente válido para ser parseado pelo AST.
- O mapear só inclui os arquivos casados pelas negações (`!`) do `.gitignore`.

## Estrutura sugerida

```
ferramentas/
├── mapear.py
├── extrator.py
├── aplicador.py
├── README.md
├── CHANGELOG.md
└── test/            # arquivos intermediários (mapear, respostas, patches)
```