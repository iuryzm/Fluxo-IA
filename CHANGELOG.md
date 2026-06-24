# Changelog

Todas as mudanças notáveis deste projeto são documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

> ℹ️ **Nota:** as seções `[Unreleased]` e `[WorkingAt]` são lidas
> automaticamente pelo `mapear.py` e incluídas no mapa enviado à IA. Use-as
> para registrar o contexto do que está sendo desenvolvido agora — assim a IA
> recebe esse status junto com a arquitetura do projeto.

## [Future]
- Estender a lógica de exclusão (`--excluir` / `.resumoignore`) ao `extrator.py`,
  para que arquivos fora do mapa também não possam ser pedidos por caminho — hoje
  só o `mapear.py` aplica os padrões.

## [WorkingAt]
- Corrigir o problema:
  ````bash
  python .\main.py extrair .\test\extrator_in.json ..\VisualizadorPN .\test\extrator_out.md                        
  🔍 Lendo as requisições da IA...
  ✅ Extração concluída! Arquivo gerado em: .\test\extrator_out.md (com instruções do aplicador anexadas)
  ````
  - Arquivo de entrada (test/extrator_in.json):
    ````json
    {
      "arquivos_completos": [],
      "classes": {},
      "funcoes": {
        "componentes/fluxos_view.py": ["DialogFluxos._on_grupo_cols_global", "DialogFluxos._on_selecao_mudou"]
      }
    }
    ````
  - Segue a resposta que a IA nos deu em relação ao código enviado:
    ````markdown
    # Tarefa: suporte a extração de métodos de classe no extrator

    ## Problema
    Hoje o extrator resolve `arquivos_completos`, `classes` (extrai a classe inteira) e `funcoes` (apenas funções de nível de módulo). Ao pedir um método de classe via `"funcoes": {"arq.py": ["NomeClasse.nome_metodo"]}`, o extrator falha com "Nenhuma das classes/funções solicitadas foi encontrada".

    Causa provável: a busca de `funcoes` só varre nós `ast.FunctionDef`/`ast.AsyncFunctionDef` cujo pai é o módulo, e não desce para dentro de nós `ast.ClassDef`. Por isso `DialogFluxos._on_selecao_mudou` é procurado como uma função de nível de módulo com esse nome literal, não existe no topo do arquivo, e é reportado como ausente.

    ## O que implementar
    Quando um alvo em `funcoes` contiver um ponto (formato `"Classe.metodo"`), o extrator deve:

    1. Localizar o nó `ast.ClassDef` cujo nome seja a parte ANTES do ponto.
    2. Dentro do corpo dessa classe, localizar o `ast.FunctionDef`/`ast.AsyncFunctionDef` cujo nome seja a parte DEPOIS do ponto.
    3. Extrair o código-fonte do método, do início do primeiro decorator (se houver) até o fim do corpo, usando os mesmos `lineno`/`end_lineno` já usados para funções de módulo.
    4. Em caso de falha, reportar qual parte faltou ("classe X não encontrada" vs. "método Y não encontrado na classe X"), em vez da mensagem genérica de ausência.

    ## Retrocompatibilidade
    Alvos SEM ponto continuam resolvendo como função de nível de módulo, exatamente como hoje. Nenhuma mudança de comportamento para `arquivos_completos` e `classes`.

    ## Caso de teste
    Extrair `DialogFluxos._on_selecao_mudou` de `componentes/fluxos_view.py` via `"funcoes": {"componentes/fluxos_view.py": ["DialogFluxos._on_selecao_mudou"]}` deve devolver o código-fonte do método (com seus decorators, se houver), e não "não encontrado".

    ## Observações de robustez
    - Suportar mais de um método da mesma classe na mesma lista (ex.: `["DialogFluxos._on_selecao_mudou", "DialogFluxos._construir"]`).
    - Suportar métodos com decorators (`@staticmethod`, `@property`, etc.): a extração deve incluir a(s) linha(s) de decorator.
    - Se houver classes aninhadas ou nomes repetidos, casar pela classe de nível mais externo cujo nome bate; documentar essa escolha caso ocorra ambiguidade.
    ````

## [Unreleased]
- No itens.

## [1.1.0] - 2026.06.22
### Adicionado
- **`main.py` (ponto de entrada único)**: despachante com os subcomandos `mapear`,
  `extrair` e `aplicar`, que delegam para as funções `executar*` de cada módulo
  sem duplicar lógica. Aceita os mesmos argumentos dos scripts originais.
- **Ação `trecho` (edição por âncora) no `aplicador.py`**: substitui, insere ou
  apaga **poucas linhas** dentro de um nó — ou de um arquivo, via
  `"tipo": "arquivo"` — sem reescrever a função/classe inteira. A IA fornece uma
  âncora (um trecho existente) e o código novo; o script procura a âncora
  **apenas dentro do escopo do alvo** e exige casamento único (0 ou 2+
  ocorrências não gravam nada). `posicao` controla o resultado: `substituir`
  (com código vazio = apagar), `antes` ou `depois`. O casamento da âncora é
  normalizado, ignorando indentação e espaços à direita.
- **Integração com a área de transferência (`clipboard.py`)**: novo módulo de
  dependência zero (PowerShell no Windows, `pbcopy`/`pbpaste` no macOS,
  `wl-copy`/`xclip`/`xsel` no Linux, sempre em UTF-8). A flag `--copiar`
  (`mapear.py` e `extrator.py`) joga a saída na área de transferência; a flag
  `--colar` (`extrator.py` e `aplicador.py`) lê a resposta da IA de lá,
  dispensando o arquivo `resposta_ia`. Fecha o ciclo com o chat sem salvar
  arquivos intermediários. Degradação graciosa: sem utilitário de clipboard na
  máquina, o `--copiar` apenas avisa e o trabalho não se perde.
- **Visualizador de diff em HTML (`--html-diff`) no `aplicador.py`**: gera uma
  página colorida no estilo GitHub (números de linha, contadores de `+`/`−`, modo
  escuro automático e seção de avisos/erros) a partir do diff unificado e a abre
  no navegador. Aceita um caminho para salvar o HTML; sem valor, usa um arquivo
  temporário. Reaproveita o `_gerar_diff` que já existia.

### Alterado
- **Renomeação do gerador de mapa**: `gerar_mapa.py` passou a se chamar
  `mapear.py`, e o subcomando correspondente no `main.py` passou de `mapa` para
  `mapear`.
- **`INSTRUCOES_IA` (`aplicador.py`)**: guia estendido para documentar a nova
  ação `trecho` (âncoras, `posicao` e regras). Como o `extrator.py` importa essa
  constante, a mudança aparece automaticamente na saída da extração.
- **CLI de `extrator.py` e `aplicador.py`**: o posicional `resposta_ia` passou a
  ser opcional quando se usa `--colar`, já que a resposta vem da área de
  transferência.

### Corrigido
- **Indentação dupla em blocos indentados (`indexar_blocos_codigo`)**: o
  `.strip()` aplicado a cada bloco de código removia a indentação apenas da
  **primeira** linha, desalinhando o trecho e fazendo o
  `textwrap.dedent`/`_reindentar` indentarem em dobro quando a IA enviava um
  código já indentado (ex.: um fragmento de dentro de um método). O resultado
  falhava no guarda-corpo de sintaxe e bloqueava operações `trecho`,
  `substituir` e `adicionar` legítimas. Agora a indentação da primeira linha é
  preservada — removem-se apenas as linhas em branco nas pontas. (O guarda-corpo
  nunca chegou a gravar arquivo inválido em disco; apenas recusava a aplicação.)
- **Mensagem do guarda-corpo de parsing (`aplicador.py`)**: quando o arquivo-alvo
  não é Python válido, o aviso agora orienta a corrigir a sintaxe e rodar de novo,
  ou a usar `"acao": "arquivo"`.

## [1.0.2] - 2026.06.17

### Changed
- **Formato de saída da IA (`INSTRUCOES_IA`)**: A instrução agora exige que a IA agrupe todos os trechos de código modificados em um **único bloco de código**, utilizando comentários explícitos (`# --- id=<codigo_id> ---`) para separar os arquivos/métodos. Isso facilita a cópia do código pelo usuário.
- **Parser de código (`indexar_blocos_codigo`)**: A lógica de extração foi reescrita para fatiar o texto baseando-se nos novos comentários separadores via Regex, em vez de depender de múltiplos blocos markdown separados.

### Fixed
- **Quebra de renderização no chat**: Correção de um problema onde o renderizador Markdown fatiaria visualmente o script ao tentar imprimi-lo ou copiá-lo. As crases (` ``` `) de delimitação do prompt agora são geradas dinamicamente via variáveis/f-strings no código Python.

## [1.0.1] - 2026.06.17
### Adicionado
- `extrator.py` agora anexa automaticamente, ao fim do Markdown gerado, as
  instruções de formato do `aplicador.py` (plano + blocos de código). Isso fecha
  o ciclo do pipeline: a IA recebe o código extraído já acompanhado do guia de
  como devolver a solução, sem precisar rodar `aplicador.py --instrucoes` à parte.
- Flag `--sem-instrucoes` no `extrator.py` para suprimir esse anexo e gerar só o
  código puro.
### Alterado
- `extrator.py` passou a importar a constante `INSTRUCOES_IA` do `aplicador.py`
  (que precisa estar na mesma pasta). Se o `aplicador.py` não for encontrado, a
  extração segue normalmente, apenas sem o anexo e com um aviso.

## [1.0.0] - 2026.06.16

Primeira versão documentada do fluxo **Mapear · Extrair · Aplicar**.

### Adicionado

#### `gerar_mapa.py`
- Geração de um mapa em Markdown da arquitetura do projeto a partir das linhas
  de negação (`!`) do `.gitignore`.
- Análise via AST de arquivos `.py`: classes (com herança e docstring), funções
  e métodos (com argumentos, anotação de retorno e docstring) e imports.
- Listagem separada de arquivos não-Python (configs), com prévia configurável
  das primeiras linhas e detecção heurística de binários (conteúdo omitido).
- Suporte a exclusões via flag `--excluir` e via arquivo `.resumoignore` na raiz
  do projeto (padrões glob).
- Flag `--linhas-config` para controlar o tamanho da prévia de arquivos de config.
- Extração automática das seções `[Unreleased]` e `[WorkingAt]` do `CHANGELOG.md`
  para anexar o status atual ao mapa.
- Bloco de instruções para a IA responder no formato JSON esperado pelo `extrator.py`.

#### `extrator.py`
- Extração cirúrgica de código com base no JSON de requisição da IA.
- Suporte às chaves `arquivos_completos`, `classes` e `funcoes`.
- Recorte de classes e funções/métodos individuais via AST, sem precisar enviar
  o arquivo inteiro.
- Fallback de parsing do JSON: tenta o bloco ```` ```json ````; se falhar,
  procura o primeiro `{` e o último `}` do texto.

#### `aplicador.py`
- Aplicação de mudanças localizando o alvo pelo **nome** via AST (independente
  de número de linha).
- Ações `substituir`, `adicionar` e `arquivo`, com tipos `funcao`, `classe` e
  `metodo` (`"Classe.metodo"`).
- Re-indentação automática do código recebido para a coluna correta do nó.
- Inserção de métodos novos no fim do corpo da classe, respeitando a indentação.
- **Dry-run por padrão**; gravação apenas com `--aplicar`.
- Criação de backups `.bak` por padrão (desativável com `--sem-backup`).
- Guarda-corpo de sintaxe: arquivos `.py` cujo resultado não faça *parse* não
  são alterados.
- Geração de patch unificado combinado (`--diff`) aplicável com `git apply`.
- Flag `--instrucoes` para imprimir o guia de formato para a IA.