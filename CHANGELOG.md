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
- Precisão por nome em `ItemExtraido.encontrado`: hoje o `extrator.py` só sabe
  *quantos* nós casaram (não *quais*), então o campo só é marcado quando todos os
  itens pedidos de um arquivo são localizados. Reportar isso por nó depende de
  expor o resultado no `ExtratorAST`.
- Possibilitar a IA de alterar o CHANGELOG.md também.
- Docstrings are important.
- 1º monte um plano de trabalho. Depois iremos executar.

## [WorkingAt]
- Construir a camada de GUI (PySide6), isolada em `pyresumidor/gui/` — o core
  permanece zero-dependência e a CLI segue funcionando sozinha.
- **Arquitetura travada:** um menu lateral e um `QStackedWidget` de páginas
  *compartilhados*; abas no topo representam projetos e só trocam qual objeto
  `Projeto` as páginas leem/escrevem. Quatro páginas: Identificar, Mapear,
  Extrair, Aplicar.
- Separação leve (não MVC formal por tela): `Projeto` como model, página como
  view, controller fino disparando o core numa *worker thread* (`QThread`/
  `QRunnable`) para não travar a UI. Promover uma tela a presenter só se ela
  crescer demais.
- A GUI **não** conversa com IA: orquestra o vaivém clipboard/arquivo
  (Identificar → Mapear → cola resposta → Extrair → cola resposta → Aplicar),
  consumindo os objetos `Resultado*` que o core agora devolve.
- **Próximo passo (Fase 2):** esqueleto — janela, abas de projeto, menu lateral
  e as quatro páginas como stubs, sem ligação com o backend ainda.
- A seguir: persistência de projeto (salvar/carregar, recentes, histórico de
  comandos), estatísticas por comando e gráfico de evolução do tamanho do
  projeto via QtCharts (sem QtWebEngine).

## [Unreleased]
- Sem itens.

## [1.4.0] - 2026.06.26
### Added
- **Pacote instalável `pyresumidor`**: o projeto deixou de ser um conjunto de
  scripts soltos e passou a um pacote Python com a estrutura `core/` (lógica
  zero-dependência), `cli/` (interface de linha de comando) e `gui/` (reservada
  para a interface gráfica). Entrada por `python -m pyresumidor` e, quando
  instalado, pelo comando `pyresumidor`.
- **Objetos de resultado estruturado (`core/resultados.py`)**: `ResultadoMapear`,
  `ResultadoExtrair` (com `ItemExtraido`), `ResultadoAplicar` (com
  `ResultadoArquivoAplicado`) e a exceção `ErroEntrada`. Os pontos de entrada do
  core agora devolvem esses dataclasses em vez de imprimir e encerrar o processo —
  base para a futura GUI consumir o mesmo backend que a CLI.
- **`ResultadoMapear` contabiliza linhas por arquivo e total do projeto**, insumo
  direto para o futuro gráfico de evolução do tamanho do projeto.
- **`pyproject.toml`**: metadados do pacote, `requires-python >= 3.9` e grupos de
  dependência opcionais — `dev` (`pytest`) e `gui` (`PySide6`). O core de runtime
  permanece sem dependências externas; pytest e PySide6 nunca entram nos
  requisitos de quem só usa o toolkit.
- **Suíte de testes (`tests/`, pytest)**: 14 testes cobrindo o contrato dos
  objetos de resultado, contagem de linhas, exclusão de arquivos, erro-como-dado
  (entrada ausente vira `sucesso=False`/`erros`), e regressões nomeadas —
  preservação de decorador na extração, desambiguação da notação `"Classe.metodo"`
  e o guarda-corpo que recusa gravar `.py` com sintaxe inválida.

### Changed
- **Pontos de entrada do core não usam mais `sys.exit` nem `print` para comunicar
  resultado**: `mapear_repositorio`, `executar_extracao` e `aplicador.executar`
  retornam um objeto `Resultado*`; falhas de entrada viram `ErroEntrada` capturada
  e transformada em dado (`sucesso=False`, `erros=[...]`). A apresentação no
  console (cores ANSI, abertura do navegador para o `--html-diff`) e a definição do
  código de saída do processo passaram a ser responsabilidade exclusiva da camada
  `cli/`.
- **Invocação pela linha de comando**: `python main.py <comando>` foi aposentado em
  favor de `python -m pyresumidor <comando>`. Os subcomandos, argumentos e flags
  permanecem idênticos — nenhuma mudança no comportamento para o usuário final.
- **Imports internos** passaram a ser relativos ao pacote (`from . import ...`),
  eliminando a antiga descoberta por `sys.path` (o "clipboard ao lado deste
  script"); a resolução do `clipboard` e de `INSTRUCOES_IA` agora é determinística,
  mantendo a degradação graciosa quando o módulo opcional está ausente.
- **`extrator.processar_arquivo`** passou a retornar `(markdown, n_encontrados)`
  em vez de só o Markdown, permitindo ao chamador saber quantos dos nós pedidos
  casaram sem inspecionar a string de saída.

## [1.3.0] - 2026.06.25
### Added
- **Feat:** Adicionada colorização ANSI na saída do console do `aplicador.py` para facilitar a leitura de diffs e mensagens de status.
- **Docs:** Inseridas docstrings detalhadas nas classes e funções principais dos arquivos `aplicador.py`, `clipboard.py`, `extrator.py`, `main.py` e `mapear.py`.
- **Feat:** `aplicador.py` — `_deslocar_bloco`, helper que desloca um bloco por N
  colunas preservando a indentação relativa.

### Changed
- **Fix:** `aplicador.py` — a `acao: "trecho"` agora posiciona o código novo por
  indentação WYSIWYG (deslocamento por `delta` entre a coluna autorada e a real da
  âncora), em vez de re-indentar tudo para a coluna da âncora. Corrige inserções num
  escopo mais raso que a âncora (ex.: funções de nível de módulo depois de uma âncora
  dentro de outra função, que antes saíam indentadas como código aninhado).
- **Docs:** Regras 4 e 7 das instruções do `aplicador.py` reescritas para refletir a
  semântica WYSIWYG do `trecho`.

## [1.2.0] - 2026.06.24
### Added
- **Extração de métodos de classe no `extrator.py`**: alvos em `"funcoes"` agora
  aceitam a notação `"Classe.metodo"` (ex.: `"DialogFluxos._on_selecao_mudou"`),
  extraindo apenas o método pedido. O `ExtratorAST` rastreia a classe que está
  visitando e casa o método no escopo da classe nomeada — eliminando a
  ambiguidade do nome solto, que casaria em qualquer classe ou no nível de
  módulo. A extração inclui os decoradores do nó (do primeiro `@` até o fim do
  corpo) e dedenta o trecho para leitura limpa; cobre também `async def`. Pedir a
  classe inteira em paralelo não duplica o método. Retrocompatível: alvos sem
  ponto continuam resolvendo como função de nível de módulo, sem mudança para
  `arquivos_completos` e `classes`.

### Changed
- **`INSTRUCOES_IA` do `mapear.py`**: o guia enviado à IA passou a documentar a
  notação `"Classe.metodo"` em `"funcoes"` (com exemplo) e ganhou uma regra
  orientando a pedir métodos sempre pontilhados — alinhado à convenção que o
  `aplicador.py` já usa (`"tipo": "metodo"`, `"alvo": "Classe.metodo"`).

## [1.1.0] - 2026.06.22
### Added
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

### Changed
- **Renomeação do gerador de mapa**: `gerar_mapa.py` passou a se chamar
  `mapear.py`, e o subcomando correspondente no `main.py` passou de `mapa` para
  `mapear`.
- **`INSTRUCOES_IA` (`aplicador.py`)**: guia estendido para documentar a nova
  ação `trecho` (âncoras, `posicao` e regras). Como o `extrator.py` importa essa
  constante, a mudança aparece automaticamente na saída da extração.
- **CLI de `extrator.py` e `aplicador.py`**: o posicional `resposta_ia` passou a
  ser opcional quando se usa `--colar`, já que a resposta vem da área de
  transferência.

### Fixed
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
### Added
- `extrator.py` agora anexa automaticamente, ao fim do Markdown gerado, as
  instruções de formato do `aplicador.py` (plano + blocos de código). Isso fecha
  o ciclo do pipeline: a IA recebe o código extraído já acompanhado do guia de
  como devolver a solução, sem precisar rodar `aplicador.py --instrucoes` à parte.
- Flag `--sem-instrucoes` no `extrator.py` para suprimir esse anexo e gerar só o
  código puro.
### Changed
- `extrator.py` passou a importar a constante `INSTRUCOES_IA` do `aplicador.py`
  (que precisa estar na mesma pasta). Se o `aplicador.py` não for encontrado, a
  extração segue normalmente, apenas sem o anexo e com um aviso.

## [1.0.0] - 2026.06.16

Primeira versão documentada do fluxo **Mapear · Extrair · Aplicar**.

### Added

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
- Fallback de parsing do JSON: tenta o bloco ` ```json `; se falhar,
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