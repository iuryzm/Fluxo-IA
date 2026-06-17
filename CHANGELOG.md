# Changelog

Todas as mudanças notáveis deste projeto são documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

> ℹ️ **Nota:** as seções `[Unreleased]` e `[WorkingAt]` são lidas
> automaticamente pelo `gerar_mapa.py` e incluídas no mapa enviado à IA. Use-as
> para registrar o contexto do que está sendo desenvolvido agora — assim a IA
> recebe esse status junto com a arquitetura do projeto.

## [Future]
- No itens.

## [WorkingAt]
- No itens.

## [Unreleased]
- No itens.

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
