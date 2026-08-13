import ast
import argparse
import fnmatch
from pathlib import Path
from .resultados import ResultadoMapear, ErroEntrada
import sys

# O clipboard é opcional: sem ele, --copiar apenas avisa.
try:
    from . import clipboard
except ImportError:
    clipboard = None

class AnalisadorAST(ast.NodeVisitor):
    """Analisador AST encarregado de catalogar imports, assinaturas e as primeiras linhas de docstrings estruturais."""
    def __init__(self):
        self.resultado = []
        self.classe_atual = None
        self.imports = []

    def visit_Import(self, no):
        for alias in no.names:
            self.imports.append(f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
        self.generic_visit(no)

    def visit_ImportFrom(self, no):
        modulo = no.module if no.module else ""
        nomes = [alias.name for alias in no.names]
        self.imports.append(f"from {modulo} import {', '.join(nomes)}")
        self.generic_visit(no)

    def visit_ClassDef(self, no):
        # Captura as classes base (herança)
        bases = []
        for base in no.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Tenta reconstruir o nome completo (ex: modulo.Classe) sem quebrar em casos aninhados
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    bases.append(base.attr)

        heranca = f"({', '.join(bases)})" if bases else ""
        self.resultado.append(f"\n* **`class {no.name}{heranca}:`**")

        docstring = ast.get_docstring(no)
        if docstring:
            primeira_linha = docstring.strip().split('\n')[0]
            self.resultado.append(f"  * *Doc:* {primeira_linha}")

        self.classe_atual = no.name
        self.generic_visit(no)
        self.classe_atual = None

    def visit_FunctionDef(self, no):
        # Ignora funções privadas/mágicas (opcional, comente as duas linhas abaixo se quiser ver os def __init__)
        # if no.name.startswith("__") and no.name != "__init__":
        #      return

            prefixo = "  * " if self.classe_atual else "* "
            argumentos = [arg.arg for arg in no.args.args if arg.arg != 'self']
            args_formatados = ", ".join(argumentos)

            retorno = ""
            if no.returns:
                try:
                    retorno = f" -> {ast.unparse(no.returns)}"
                except Exception:
                    pass

            self.resultado.append(f"{prefixo}`def {no.name}({args_formatados}){retorno}`")

            docstring = ast.get_docstring(no)
            if docstring:
                primeira_linha = docstring.strip().split('\n')[0]
                self.resultado.append(f"  {prefixo}  *Doc:* {primeira_linha}")

def processar_arquivo_py(caminho_arquivo: Path, caminho_base: Path) -> str:
    """Lê um arquivo .py e retorna seu resumo em Markdown."""
    caminho_relativo = caminho_arquivo.relative_to(caminho_base)
    try:
        conteudo = caminho_arquivo.read_text(encoding="utf-8")
        arvore = ast.parse(conteudo)

        doc_modulo = ast.get_docstring(arvore)
        doc_texto = f"\n> *{doc_modulo.strip().split(chr(10))[0]}*\n" if doc_modulo else ""

        analisador = AnalisadorAST()
        analisador.visit(arvore)

        resumo = f"### 📁 `{caminho_relativo}`\n{doc_texto}"

        if analisador.imports:
            imports_str = ", ".join(analisador.imports[:5])
            if len(analisador.imports) > 5:
                imports_str += ", ..."
            resumo += f"**Dependências:** `{imports_str}`\n"

        if not analisador.resultado:
            resumo += "*Nenhuma classe ou função encontrada.*\n"
        else:
            resumo += "\n".join(analisador.resultado) + "\n"
        return resumo

    except Exception as e:
        return f"### 📁 `{caminho_relativo}`\n*Erro ao ler arquivo: {e}*\n"

def _parece_binario(caminho_arquivo: Path) -> bool:
    """Heurística do Git: arquivo é binário se tem byte nulo ou não decodifica em UTF-8.

    Evita despejar texto sem sentido (imagens, .pkl, .db, .ico, etc.) no mapear.
    """
    try:
        amostra = caminho_arquivo.read_bytes()[:65536]
    except Exception:
        return True  # se nem dá pra ler como bytes, trata como binário (sem prévia)

    if b"\x00" in amostra:
        return True

    try:
        amostra.decode("utf-8")
    except UnicodeDecodeError as e:
        # Se o erro está bem no fim do bloco, pode ser um caractere multibyte
        # cortado pelo limite de leitura — nesse caso, tratamos como texto.
        if e.start >= len(amostra) - 3:
            return False
        return True
    return False

def processar_arquivo_outro(caminho_arquivo: Path, caminho_base: Path, max_linhas_preview: int = 20) -> str:
    """Lista um arquivo não-Python (config, etc.) com uma prévia opcional do conteúdo.

    A IA não consegue 'parsear' esses arquivos como faz com .py, então o objetivo aqui
    é apenas anunciar que o arquivo existe (com seu caminho) e dar uma amostra do conteúdo
    para que ela decida se precisa pedi-lo inteiro via "arquivos_completos".
    """
    caminho_relativo = caminho_arquivo.relative_to(caminho_base)
    extensao = caminho_arquivo.suffix.lstrip('.') or "sem extensão"
    resumo = f"### ⚙️ `{caminho_relativo}`\n"

    try:
        tamanho_kb = caminho_arquivo.stat().st_size / 1024
    except Exception:
        tamanho_kb = 0.0

    # Binários: lista só os metadados, sem despejar conteúdo ilegível no mapear.
    if _parece_binario(caminho_arquivo):
        resumo += f"*(tipo: `{extensao}` · {tamanho_kb:.1f} KB · binário — conteúdo omitido)*\n"
        return resumo

    resumo += f"*(tipo: `{extensao}` · {tamanho_kb:.1f} KB)*\n"

    if max_linhas_preview > 0:
        try:
            linhas = caminho_arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
            preview = "\n".join(linhas[:max_linhas_preview])
            if len(linhas) > max_linhas_preview:
                preview += f"\n... (+{len(linhas) - max_linhas_preview} linhas ocultas)"
            # Usa a extensão como dica de linguagem para o bloco de código (json, yaml, toml...)
            lang = caminho_arquivo.suffix.lstrip('.')
            resumo += f"```{lang}\n{preview}\n```\n"
        except Exception as e:
            resumo += f"*Erro ao ler arquivo: {e}*\n"

    return resumo

def carregar_padroes_exclusao(diretorio_projeto: Path, excluir_cli: list) -> list:
    """Junta os padrões de exclusão do CLI (--excluir) com os do arquivo .resumoignore."""
    padroes = list(excluir_cli or [])

    arquivo_ignore = diretorio_projeto / ".resumoignore"
    if arquivo_ignore.exists():
        try:
            for linha in arquivo_ignore.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    padroes.append(linha)
            print(f"🚫 .resumoignore encontrado ({arquivo_ignore.name}).")
        except Exception as e:
            print(f"  ⚠️ Erro ao ler .resumoignore: {e}")

    if padroes:
        print(f"🚫 {len(padroes)} padrão(ões) de exclusão ativo(s): {', '.join(padroes)}")
    return padroes

def _deve_excluir(caminho_arquivo: Path, diretorio_projeto: Path, padroes: list) -> bool:
    """True se o arquivo casa com algum padrão glob (pelo caminho relativo OU pelo nome)."""
    if not padroes:
        return False
    try:
        rel = caminho_arquivo.relative_to(diretorio_projeto).as_posix()
    except ValueError:
        rel = caminho_arquivo.name
    nome = caminho_arquivo.name
    for padrao in padroes:
        if fnmatch.fnmatch(rel, padrao) or fnmatch.fnmatch(nome, padrao):
            return True
    return False

def extrair_arquivos_do_gitignore(caminho_gitignore: Path, padroes_exclusao: list = None) -> tuple:
    """Lê as negações (!) do .gitignore e separa em (arquivos_py, arquivos_outros).

    Arquivos que casam com `padroes_exclusao` (glob) ficam de fora do resumo.
    Levanta ErroEntrada se não conseguir ler o .gitignore (sem sys.exit).
    """
    padroes_exclusao = padroes_exclusao or []
    diretorio_projeto = caminho_gitignore.parent
    arquivos_py_encontrados = set()
    arquivos_outros_encontrados = set()

    try:
        linhas = caminho_gitignore.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        raise ErroEntrada(f"Erro fatal ao ler o arquivo .gitignore: {e}")

    for linha in linhas:
        linha = linha.strip()
        if linha.startswith('!') and not linha.endswith('/'):
            padrao = linha[1:]
            for arquivo_encontrado in diretorio_projeto.glob(padrao):
                if not arquivo_encontrado.is_file():
                    continue
                if _deve_excluir(arquivo_encontrado, diretorio_projeto, padroes_exclusao):
                    continue
                if arquivo_encontrado.suffix == '.py':
                    arquivos_py_encontrados.add(arquivo_encontrado.resolve())
                else:
                    arquivos_outros_encontrados.add(arquivo_encontrado.resolve())

    return sorted(arquivos_py_encontrados), sorted(arquivos_outros_encontrados)

def extrair_contexto_changelog(diretorio_projeto: Path) -> str:
    """Busca e extrai de forma automatizada o conteúdo sob as tags '[Unreleased]' e '[WorkingAt]' no arquivo CHANGELOG.md."""
    changelog_path = diretorio_projeto / "CHANGELOG.md"
    print(f"🔍 Procurando CHANGELOG em: {changelog_path}")

    if not changelog_path.exists():
        print("  ⚠️ CHANGELOG.md não encontrado.")
        return ""

    try:
        linhas = changelog_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"  ❌ Erro ao ler CHANGELOG.md: {e}")
        return f"\n*Erro ao ler CHANGELOG.md: {e}*\n"

    capturando = False
    trecho_extraido = []
    secoes_alvo = ["## [Unreleased]", "## [WorkingAt]"]

    for linha in linhas:
        linha_limpa = linha.strip()

        # Verifica se chegamos a um título '## '
        if linha_limpa.startswith("## "):
            # Se for uma das seções alvo, liga a captura
            if any(linha_limpa.startswith(alvo) for alvo in secoes_alvo):
                capturando = True
                trecho_extraido.append(linha)
            else:
                # Se for qualquer outro título (ex: ## [1.0.0]), desliga a captura
                capturando = False
        # Se estivermos no modo de captura, adicionamos a linha
        elif capturando:
            trecho_extraido.append(linha)

    if not trecho_extraido:
        print("  ⚠️ Nenhuma seção '[Unreleased]' ou '[WorkingAt]' encontrada no CHANGELOG.")
        return ""

    print(f"  ✅ Contexto do CHANGELOG extraído com {len(trecho_extraido)} linhas.")
    resultado = "\n# 🛠️ Status Atual e Não Publicado (CHANGELOG.md)\n"
    resultado += "\n".join(trecho_extraido) + "\n"
    return resultado

def _copiar_saida(conteudo: str) -> bool:
    """Copia o mapa para a área de transferência. Retorna True se conseguiu copiar."""
    if clipboard is None:
        return False
    try:
        clipboard.copiar(conteudo)
        return True
    except clipboard.ClipboardIndisponivel:
        return False

def mapear_repositorio(caminho_gitignore_str: str, arquivo_saida_str: str, linhas_config: int = 20,
                       excluir: list = None, copiar: bool = False):
    """Mapeia recursivamente os arquivos do projeto respeitando exclusões e o .gitignore.

    Retorna ResultadoMapear: não imprime nem encerra o processo (quem apresenta é a CLI).
    """
    cb = chr(96) * 3
    try:
        caminho_gitignore = Path(caminho_gitignore_str).resolve()
        diretorio_projeto = caminho_gitignore.parent
        if not caminho_gitignore.exists():
            raise ErroEntrada(f"O arquivo '{caminho_gitignore}' não foi encontrado.")
        padroes_exclusao = carregar_padroes_exclusao(diretorio_projeto, excluir)
        arquivos_py, arquivos_outros = extrair_arquivos_do_gitignore(caminho_gitignore, padroes_exclusao)
    except ErroEntrada as e:
        return ResultadoMapear(sucesso=False, conteudo="", caminho_saida=None,
                               arquivos_py=[], arquivos_outros=[], linhas_por_arquivo={},
                               total_linhas=0, copiado=False, erros=[str(e)])

    if not arquivos_py and not arquivos_outros:
        return ResultadoMapear(sucesso=True, conteudo="", caminho_saida=None,
                               arquivos_py=[], arquivos_outros=[], linhas_por_arquivo={},
                               total_linhas=0, copiado=False,
                               avisos=["Nenhum arquivo válido foi encontrado."])

    mapear_completo = ["# Resumo da Arquitetura do Projeto\n", "---\n"]
    for arquivo in arquivos_py:
        mapear_completo.append(processar_arquivo_py(arquivo, diretorio_projeto))
        mapear_completo.append("\n---\n")

    if arquivos_outros:
        mapear_completo.append("\n# ⚙️ Arquivos de Configuração e Outros\n")
        mapear_completo.append(
            "*Estes arquivos não são código Python e, portanto, não foram analisados por classe/função. "
            "Para vê-los, peça-os via `\"arquivos_completos\"`.*\n"
        )
        mapear_completo.append("---\n")
        for arquivo in arquivos_outros:
            mapear_completo.append(processar_arquivo_outro(arquivo, diretorio_projeto, linhas_config))
            mapear_completo.append("\n---\n")

    instrucoes_ia = (
        "# 🤖 INSTRUÇÕES ESTRITAS PARA A IA\n"
        "Você está analisando a arquitetura de um projeto. Ao receber uma tarefa do usuário baseada neste mapear, "
        "você deve informar quais arquivos, classes ou funções precisa visualizar o código-fonte para implementar a solução.\n\n"
        "Para que o script de extração automática do usuário funcione, você **DEVE** incluir em sua resposta um bloco "
        "de código contendo um objeto JSON estrito com o mapeamento do que você precisa.\n\n"
        "Siga EXATAMENTE este formato:\n\n"
        + cb + "json\n"
        "{\n"
        "  \"arquivos_completos\": [\n"
        "    \"caminho/relativo/do/arquivo1.py\",\n"
        "    \"caminho/relativo/do/config.yaml\"\n"
        "  ],\n"
        "  \"classes\": {\n"
        "    \"caminho/relativo/do/arquivo2.py\": [\"NomeDaClasse\", \"OutraClasse\"]\n"
        "  },\n"
        "  \"funcoes\": {\n"
        "    \"caminho/relativo/do/arquivo3.py\": [\"nome_da_funcao\", \"outra_funcao\", \"NomeDaClasse.nome_do_metodo\"]\n"
        "  },\n"
        "  \"trechos\": [\n"
        "    {\"arquivo\": \"caminho/relativo/do/arquivo4.py\", \"alvo\": \"NomeDaClasse.metodo\", \"fatia\": \"primeiras:5\"},\n"
        "    {\"arquivo\": \"caminho/relativo/do/arquivo4.py\", \"fatia\": \"primeiras:15\"}\n"
        "  ]\n"
        "}\n"
        + cb + "\n\n"
        "**Regras do JSON:**\n"
        "1. Use as chaves `\"arquivos_completos\"`, `\"classes\"` e `\"funcoes\"`.\n"
        "2. Se não precisar de itens para uma das chaves, deixe a lista ou o dicionário vazio (ex: `\"arquivos_completos\": []`).\n"
        "3. Peça `\"arquivos_completos\"` APENAS se precisar modificar o escopo global ou entender o arquivo inteiro. "
        "Para economizar contexto, dê preferência máxima a extrair `\"classes\"` ou `\"funcoes\"` isoladas.\n"
        "4. Arquivos listados na seção **'⚙️ Arquivos de Configuração e Outros'** (ex: `.json`, `.yaml`, `.toml`, `.env`, `.cfg`) "
        "NÃO são código Python e só podem ser obtidos via `\"arquivos_completos\"`. Nunca tente pedir uma `\"classe\"` ou "
        "`\"funcao\"` desses arquivos.\n"
        "5. Para pedir um MÉTODO de uma classe, use a notação `\"Classe.metodo\"` dentro de "
        "`\"funcoes\"` (ex: `\"NomeDaClasse.nome_do_metodo\"`). Não peça o método pelo nome solto: "
        "ele é ambíguo (pode existir em várias classes) e não casa. Para a classe inteira, "
        "continue usando `\"classes\"`.\n"
        "6. **Não copie texto do mapa como âncora de `\"trecho\"`.** O mapa é um "
        "RESUMO com perdas: a linha `**Dependências:**` mostra só os 5 primeiros "
        "imports (truncados com `, ...`) e achata imports multilinha numa única "
        "linha, sem parênteses nem vírgulas — ou seja, esse texto quase nunca "
        "existe igual no disco. Para ancorar com segurança, peça antes o código "
        "via `\"funcoes\"`/`\"classes\"`/`\"arquivos_completos\"` e copie a âncora "
        "dos BYTES EXATOS que receber de volta.\n"
        "7. Para VER (não editar) só um pedaço de código — os imports do topo, a "
        "assinatura real de uma função, a indentação de um método — use a chave "
        "`\"trechos\"`: uma lista de objetos "
        "`{\"arquivo\": ..., \"alvo\": opcional, \"fatia\": \"primeiras:N\"|\"ultimas:N\"}`. "
        "Com `\"alvo\"` (nome de função/classe/`\"Classe.metodo\"`, ou nome de uma "
        "CONSTANTE de nível de módulo, ex. `\"LIMITE\"`) a fatia conta as "
        "linhas do nó; sem `\"alvo\"`, conta do arquivo inteiro (ideal para ver os "
        "imports do topo sem pagar o arquivo todo — mais barato que "
        "`\"arquivos_completos\"`, cf. regra 6). O resultado é sempre um RECORTE "
        "PARCIAL, marcado como tal: serve para LER/entender, NUNCA como âncora de "
        "`\"trecho\"` nem como definição completa para editar. Para editar, peça o nó "
        "inteiro via `\"funcoes\"`/`\"classes\"` (função/classe/método). Para uma "
        "CONSTANTE de módulo, `\"trechos\"` só serve para LER: `\"funcoes\"`/`\"classes\"` "
        "não suportam constante — para editar, peça o arquivo via "
        "`\"arquivos_completos\"`.\n"
        "8. Chave OPCIONAL de topo `\"sem_instrucoes\": true` (irmã de "
        "`\"arquivos_completos\"`/`\"classes\"`/`\"funcoes\"`/`\"trechos\"`, NÃO um item "
        "dentro delas): se a tarefa é só LER/entender o código e você NÃO vai devolver "
        "um plano de edição, defina-a como `true` para não anexar as instruções do "
        "aplicador à saída, economizando tokens. Se você VAI propor edições (plano + "
        "blocos), omita a chave ou deixe `false` — você vai precisar das instruções.\n"
    )
    mapear_completo.append(instrucoes_ia)

    contexto_changelog = extrair_contexto_changelog(diretorio_projeto)
    if contexto_changelog:
        mapear_completo.append(contexto_changelog)

    conteudo = "\n".join(mapear_completo)

    def _rel(a):
        try:
            return str(a.relative_to(diretorio_projeto))
        except ValueError:
            return str(a)

    linhas_por_arquivo = {}
    for arquivo in list(arquivos_py) + list(arquivos_outros):
        rel = _rel(arquivo)
        try:
            linhas_por_arquivo[rel] = len(arquivo.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            linhas_por_arquivo[rel] = 0
    total_linhas = sum(linhas_por_arquivo.values())

    rel_py = [_rel(a) for a in arquivos_py]
    rel_outros = [_rel(a) for a in arquivos_outros]

    arquivo_saida = Path(arquivo_saida_str).resolve()
    try:
        arquivo_saida.write_text(conteudo, encoding="utf-8")
    except Exception as e:
        return ResultadoMapear(sucesso=False, conteudo=conteudo, caminho_saida=None,
                               arquivos_py=rel_py, arquivos_outros=rel_outros,
                               linhas_por_arquivo=linhas_por_arquivo, total_linhas=total_linhas,
                               copiado=False, erros=[f"Erro ao salvar o arquivo: {e}"])

    copiado = _copiar_saida(conteudo) if copiar else False
    return ResultadoMapear(sucesso=True, conteudo=conteudo, caminho_saida=str(arquivo_saida),
                           arquivos_py=rel_py, arquivos_outros=rel_outros,
                           linhas_por_arquivo=linhas_por_arquivo, total_linhas=total_linhas,
                           copiado=copiado)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera um resumo do código Python baseado no .gitignore.")
    parser.add_argument("gitignore_path", help="Caminho para o arquivo .gitignore do projeto alvo.")
    parser.add_argument("output_path", help="Caminho e nome do arquivo .md de saída.")
    parser.add_argument(
        "--linhas-config",
        type=int,
        default=20,
        help="Nº de linhas de prévia exibidas para arquivos de config/outros. Use 0 para listar sem prévia (default: 20).",
    )
    parser.add_argument(
        "--excluir",
        nargs="*",
        default=[],
        metavar="PADRAO",
        help="Padrões glob de arquivos a NÃO incluir no resumo (ex: --excluir *.env segredos.yaml src/local_*.py). "
             "Soma-se aos padrões do arquivo .resumoignore na raiz do projeto, se existir.",
    )
    parser.add_argument(
        "--copiar",
        action="store_true",
        help="Também copia o mapear para a área de transferência, pronto para colar no chat da IA.",
    )

    args = parser.parse_args()
    mapear_repositorio(args.gitignore_path, args.output_path, args.linhas_config, args.excluir, args.copiar)

# Como utilizar
# python mapear.py <CAMINHO_DO_GITIGNORE> <CAMINHO_DO_MARKDOWN_DE_SAIDA> [--linhas-config N] [--excluir PADRAO ...] [--copiar]

# Para excluir arquivos do resumo:
#   - Pontual (CLI):   python mapear.py ../Proj/.gitignore resumo.md --excluir *.env "src/segredo.py"
#   - Persistente:     crie um .resumoignore na raiz do projeto (um padrão glob por linha; # vira comentário).

# Exemplo prático:
# python mapear.py ../MeuSuperProjeto/.gitignore ../MeuSuperProjeto/resumo_do_projeto.md
# python .\mapear.py ..\VisualizadorPN\.gitignore .\test\resumo_do_projeto.md --linhas-config 10 --excluir *.env
# python .\mapear.py ..\VisualizadorPN\.gitignore .\test\resumo_do_projeto.md --linhas-config 10 --copiar
