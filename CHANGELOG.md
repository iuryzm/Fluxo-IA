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
- Fase 6 (polimento da GUI), itens candidatos:
  - Visualizador de diff nativo mais rico na página Aplicar (hoje é texto colorido
    via QTextCharFormat; sem QtWebEngine).
  - Histórico em tabela (QTableWidget) em vez de linhas de texto, se valer a pena.
  - Tratamento de bordas e ajustes visuais conforme o uso real revelar.
- Alinhar o piso de Python real: o projeto roda em 3.14, mas `requires-python`
  declara `>=3.9` sem CI que verifique — decidir se mantém a promessa ou sobe o piso.
- `trechos` não alcança atribuições de módulo por nome (só nós de função/classe);
  ver constantes longas (ex.: INSTRUCOES_IA) exige fatia-de-arquivo sem "alvo" ou
  "arquivos_completos". Estender o extrator para resolver alvos do tipo Assign.
- O pipeline não insere whitespace puro (linhas em branco isoladas): o
  indexar_blocos_codigo remove linhas em branco das pontas dos blocos, então
  edições só-de-espaçamento precisam ser manuais.
- `adicionar` de função/método num arquivo que termina em `if __name__ ==
  "__main__"` insere a definição depois do guard; em arquivos com guard de entrada,
  inserir por âncora antes dele ou reordenar.
- No histórico de uma sequência (modo C) interrompida por um gate, o breakdown
  por-arquivo pode listar arquivos preparados mas não gravados (a contagem
  principal de gravados está correta; o breakdown é caso de borda).

## [WorkingAt]
- No itens.

### [Guidelines]
- Docstrings are important.
- 1º monte um plano de trabalho. Depois iremos executar.

## [Unreleased]
- No itens.

## [1.6.0] - 2026.07.02
### Adicionado
- Ação `adicionar_import` no aplicador: insere nomes num `from <módulo> import ...`
  via AST, imune ao formato do import no disco (linha única ou parentético
  multilinha). Não usa âncora nem `codigo_id` — recebe `modulo` e `nomes` direto
  no plano. Emite o import sempre na forma canônica (um nome por linha, entre
  parênteses), forma única e previsível para releituras futuras.
- Chave `trechos` no protocolo de extração: pede as primeiras/últimas N linhas de
  um alvo (`funcao` / `Classe` / `Classe.metodo`) ou do arquivo inteiro, no formato
  `{"arquivo", "alvo"?, "fatia": "primeiras:N"|"ultimas:N"}`. Serve para a IA ver
  imports, assinaturas ou indentação exatos sem pagar o arquivo todo em tokens. O
  resultado sai marcado como recorte parcial e nunca deve ser usado como âncora.
- Estatística por arquivo: o histórico passa a guardar o detalhamento por arquivo
  de cada Mapear (`linhas_por_arquivo`) e Aplicar (`por_arquivo` com +/− por
  arquivo). A página de Histórico/Estatísticas mostra os arquivos maiores do último
  mapa e os mais alterados do último apply. Método `resumo_historico()` centraliza
  nos dataclasses `ResultadoMapear`/`ResultadoAplicar` quais campos entram no
  histórico.
- Casamento tolerante de âncora no aplicador: quando o casamento exato (linha a
  linha) falha, um fallback colapsa o whitespace (inclusive quebras de linha) dos
  dois lados, permitindo casar uma âncora reflada contra um construto equivalente
  quebrado em várias linhas no disco. Exige casamento único.
- Diagnóstico de âncora que não casa: a mensagem de erro passa a listar as linhas
  do escopo mais próximas da âncora (por similaridade), revelando como o disco
  difere do texto ancorado.
- Modo sequenciado (modo C) no aplicar: o plano pode conter ações `comando` que
  executam comandos PowerShell, intercaladas com as edições e executadas na ordem do
  plano. Comandos podem ter gates (`espera_exit`/`espera_conter`): se o resultado
  divergir, a sequência para e as operações seguintes não rodam. Edições encadeiam em
  memória — o mesmo arquivo pode ser editado antes e depois de um comando.
- Execução com opt-in obrigatório e confirmação humana: na CLI via `--permitir-comandos`
  (confirmação por comando ou em lote com `--confirmar-lote`, timeout configurável por
  `--timeout-comando`); na GUI via diálogo de lote antes de rodar. Sem autorização
  explícita, nada é executado. A saída de cada comando (stdout/stderr/exit) é capturada
  e apresentada, pronta para colar de volta no chat com a IA.
- Chave `sem_instrucoes` no JSON de extração: a IA pode pedir para omitir as instruções
  do aplicador da saída do extrair, economizando tokens em tarefas só de leitura. A
  supressão respeita OR entre essa chave e a flag `--sem-instrucoes` da CLI.
- Botão de ajuda ("?") nas páginas Extrair e Aplicar: abre um diálogo com um
  exemplo do formato esperado (JSON de extração na página Extrair; plano + blocos
  de código e as cinco ações na página Aplicar), em fonte monoespaçada e copiável.
  Helper `_mostrar_ajuda` compartilhado na PaginaBase.

### Corrigido
- Falha silenciosa ao ancorar `trecho` sobre imports, causada por copiar a âncora
  da linha `**Dependências:**` do mapa (um resumo com perdas: truncado em 5 imports
  e achatado numa linha) em vez dos bytes do disco. Resolvido em três camadas: a
  ação `adicionar_import` (conserto de raiz), o casamento tolerante (rede de
  segurança) e regras explícitas nas instruções do mapa e do aplicador orientando a
  copiar âncoras sempre do código extraído, nunca do mapa.
- Remoção de linhas duplicadas nos handlers `_ao_concluir` das páginas Mapear e
  Aplicar (efeito colateral limpo da reescrita dos métodos).

### Interno
- Arquitetura "core prepara, UI executa": o core monta a sequência de passos (edições
  com diffs + comandos com gates) e os estados finais, sem tocar o mundo; a execução
  (gravar arquivos, rodar comandos) fica isolada em `executor_sequencia`, a única parte
  com efeito colateral, chamada pela UI com um confirmador. `aplicar_em_arquivo` foi
  refatorado num núcleo puro (`_aplicar_ops_em_texto`) para permitir o encadeamento.

## [1.5.0] - 2026.06.29
### Added
- **Interface gráfica (PySide6), isolada em `pyresumidor/gui/`**: aplicação
  completa lançada por `python -m pyresumidor.gui`. O core permanece
  zero-dependência e a CLI segue funcionando sozinha; PySide6 é dependência
  opcional (grupo `gui`), importada apenas pela camada de interface.
- **Navegação por projetos e operações**: abas no topo representam projetos
  (adicionar/fechar/renomear — a aba assume o nome da pasta-pai do `.gitignore`);
  um menu lateral e um `QStackedWidget` de páginas *compartilhados* trocam apenas
  qual `Projeto` as páginas leem. Cinco páginas: Identificar, Mapear, Extrair,
  Aplicar e Histórico/Estatísticas.
- **Execução do core fora da thread de UI (`WorkerCore`/`rodar_em_thread`)**: cada
  operação roda num `QThread` e devolve o objeto `Resultado*` por sinal, sem
  congelar a janela. Os sinais usam `QueuedConnection` com slots-método (não
  lambdas) para respeitar a afinidade de thread do Qt.
- **Página Identificar**: seleção do `.gitignore` com validação da allowlist,
  botão de ajuda explicando o formato, e dropdown de **projetos recentes**
  (persistido) para reabrir projetos sem renavegar.
- **Página Mapear/Extrair/Aplicar**: cada uma roda seu comando do core, exibe o
  resultado e copia a saída para o chat da IA. Extrair tem campo de entrada,
  checkbox de instruções e botão limpar. Aplicar separa plano (JSON) e código em
  dois campos (o usuário nunca digita crases), exige **simular antes de aplicar**,
  confirma a gravação listando os arquivos, mostra o diff colorido inline e cria
  backups `.bak`.
- **Persistência em `pyresumidor/dados/` (zero-dependência, JSON)**: estado por
  projeto, configuração do usuário (`config.json`), índice de projetos recentes e
  histórico de comandos. Gravação atômica (escreve em `.tmp` e renomeia) e leitura
  com fallback — um JSON corrompido pela limpeza do ambiente não derruba o app.
  Os artefatos ficam dentro da instalação do PyResumidor para sobreviver à limpeza
  periódica de diretórios de projeto-alvo.
- **Histórico de comandos**: cada Mapear/Extrair/Aplicar (apenas aplicação real,
  não simulação) registra entrada, saída e um resumo numérico no `projeto.json`.
- **Página Histórico/Estatísticas**: lista das execuções, contadores por comando,
  total de linhas adicionadas/removidas e **gráfico de evolução** (linhas e número
  de arquivos por mapeamento) via QtCharts — que já vem no PySide6, sem dependência
  nova. Degrada para um aviso se o QtCharts não estiver disponível.
- **Persistência e estatísticas cobertas por testes** (pytest): 23 testes novos
  somam-se aos 14 anteriores (config/projeto/recentes/histórico isolados em
  `tmp_path`, agregação de estatísticas, e a regressão de JSON malformado virando
  `ErroEntrada` em vez de derrubar a interface).

### Changed
- **`extrair_json_de_texto` não usa mais `sys.exit`**: JSON ausente ou inválido na
  resposta da IA agora levanta `ErroEntrada` (convertido em `sucesso=False`),
  fechando o último caminho do core que encerrava o processo — era o que derrubava
  a janela da GUI ao colar um JSON malformado.
- **`version` do pacote** atualizada para `1.5.0`.

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