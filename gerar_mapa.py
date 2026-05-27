import ast
import argparse
from pathlib import Path
import sys

class AnalisadorAST(ast.NodeVisitor):
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
                bases.append(f"{base.value.id}.{base.attr}")
        
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
        #     return

        prefixo = "  * " if self.classe_atual else "* "
        argumentos = [arg.arg for arg in no.args.args if arg.arg != 'self'] # 'self' é implícito, não precisamos gastar tokens
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
        
        # Pega a docstring do arquivo (módulo)
        doc_modulo = ast.get_docstring(arvore)
        doc_texto = f"\n> *{doc_modulo.strip().split(chr(10))[0]}*\n" if doc_modulo else ""
        
        analisador = AnalisadorAST()
        analisador.visit(arvore)
        
        resumo = f"### 📁 `{caminho_relativo}`\n{doc_texto}"
        
        # Adiciona os imports encontrados
        if analisador.imports:
            # Pega apenas os 5 primeiros imports ou imports internos para não poluir muito
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

def extrair_arquivos_py_do_gitignore(caminho_gitignore: Path) -> list:
    diretorio_projeto = caminho_gitignore.parent
    arquivos_py_encontrados = set() 

    try:
        linhas = caminho_gitignore.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"Erro ao ler o arquivo .gitignore: {e}")
        sys.exit(1)

    for linha in linhas:
        linha = linha.strip()
        if linha.startswith('!') and not linha.endswith('/'):
            padrao = linha[1:] 
            for arquivo_encontrado in diretorio_projeto.glob(padrao):
                if arquivo_encontrado.is_file() and arquivo_encontrado.suffix == '.py':
                    arquivos_py_encontrados.add(arquivo_encontrado.resolve())

    return sorted(list(arquivos_py_encontrados))

def extrair_secao_working_at(diretorio_projeto: Path) -> str:
    """Procura o CHANGELOG.md e extrai apenas a seção ## [WorkingAt]."""
    changelog_path = diretorio_projeto / "CHANGELOG.md"
    
    if not changelog_path.exists():
        return ""

    try:
        linhas = changelog_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return f"\n*Erro ao ler CHANGELOG.md: {e}*\n"

    capturando = False
    trecho_extraido = []

    for linha in linhas:
        linha_limpa = linha.strip()
        
        # Identifica o início da seção
        if linha_limpa.startswith("## [WorkingAt]"):
            capturando = True
            trecho_extraido.append(linha)
            continue
        
        if capturando:
            # Se encontrar outro cabeçalho '##', significa que a seção acabou
            if linha_limpa.startswith("## "):
                break
            trecho_extraido.append(linha)

    if not trecho_extraido:
        return ""

    # Formata o retorno para destacar bem no final do arquivo Markdown
    resultado = "\n# 🛠️ Status Atual (CHANGELOG.md)\n"
    resultado += "\n".join(trecho_extraido) + "\n"
    return resultado

def gerar_mapa_repositorio(caminho_gitignore_str: str, arquivo_saida_str: str):
    # Adicionamos .resolve() para converter caminhos relativos do terminal em absolutos
    caminho_gitignore = Path(caminho_gitignore_str).resolve()
    diretorio_projeto = caminho_gitignore.parent
    
    if not caminho_gitignore.exists():
        print(f"Erro: O arquivo '{caminho_gitignore}' não foi encontrado.")
        sys.exit(1)

    arquivos_para_processar = extrair_arquivos_py_do_gitignore(caminho_gitignore)
    
    if not arquivos_para_processar:
        print("⚠️ Nenhum arquivo .py válido foi encontrado.")
        sys.exit(0)
    
    mapa_completo = ["# Resumo da Arquitetura do Projeto\n"]
    mapa_completo.append("---\n")
    
    for arquivo in arquivos_para_processar:
        resumo_arquivo = processar_arquivo_py(arquivo, diretorio_projeto)
        mapa_completo.append(resumo_arquivo)
        mapa_completo.append("\n---\n")
        
    instrucoes_ia = (
        "# 🤖 INSTRUÇÕES ESTRITAS PARA A IA\n"
        "Você está analisando a arquitetura de um projeto. Ao receber uma tarefa do usuário baseada neste mapa, "
        "você deve informar quais arquivos, classes ou funções precisa visualizar o código-fonte para implementar a solução.\n\n"
        "Para que o script de extração automática do usuário funcione, você **DEVE** incluir em sua resposta um bloco "
        "de código contendo um objeto JSON estrito com o mapeamento do que você precisa.\n\n"
        "Siga EXATAMENTE este formato:\n\n"
        "```json\n"
        "{\n"
        "  \"arquivos_completos\": [\n"
        "    \"caminho/relativo/do/arquivo1.py\"\n"
        "  ],\n"
        "  \"classes\": {\n"
        "    \"caminho/relativo/do/arquivo2.py\": [\"NomeDaClasse\", \"OutraClasse\"]\n"
        "  },\n"
        "  \"funcoes\": {\n"
        "    \"caminho/relativo/do/arquivo3.py\": [\"nome_da_funcao\", \"outra_funcao\"]\n"
        "  }\n"
        "}\n"
        "```\n\n"
        "**Regras do JSON:**\n"
        "1. Use as chaves `\"arquivos_completos\"`, `\"classes\"` e `\"funcoes\"`.\n"
        "2. Se não precisar de itens para uma das chaves, deixe a lista ou o dicionário vazio (ex: `\"arquivos_completos\": []`).\n"
        "3. Peça `\"arquivos_completos\"` APENAS se precisar modificar o escopo global ou entender o arquivo inteiro. "
        "Para economizar contexto, dê preferência máxima a extrair `\"classes\"` ou `\"funcoes\"` isoladas.\n"
    )
    
    mapa_completo.append(instrucoes_ia)

    # --- EXTRAÇÃO DO CHANGELOG ---
    secao_working_at = extrair_secao_working_at(diretorio_projeto)
    if secao_working_at:
        mapa_completo.append(secao_working_at)
    # -----------------------------------------
    
    Path(arquivo_saida_str).write_text("\n".join(mapa_completo), encoding="utf-8")
    print(f"✅ Mapa gerado com sucesso em: {arquivo_saida_str}")

# Como utilizar
# python gerar_mapa.py <CAMINHO_DO_GITIGNORE> <CAMINHO_DO_MARKDOWN_DE_SAIDA>

# Exemplo prático:
# python gerar_mapa.py ../MeuSuperProjeto/.gitignore ../MeuSuperProjeto/resumo_do_projeto.md