import ast
import argparse
from pathlib import Path
import sys

class AnalisadorAST(ast.NodeVisitor):
    """
    Visita os nós da árvore de sintaxe (AST) e formata a saída em Markdown.
    """
    def __init__(self):
        self.resultado = []
        self.classe_atual = None

    def visit_ClassDef(self, no):
        self.resultado.append(f"\n* **`class {no.name}:`**")
        docstring = ast.get_docstring(no)
        if docstring:
            primeira_linha = docstring.strip().split('\n')[0]
            self.resultado.append(f"  * *Doc:* {primeira_linha}")
            
        self.classe_atual = no.name
        self.generic_visit(no)
        self.classe_atual = None

    def visit_FunctionDef(self, no):
        prefixo = "  * " if self.classe_atual else "* "
        argumentos = [arg.arg for arg in no.args.args]
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

def processar_arquivo_py(caminho_arquivo: Path) -> str:
    """Lê um arquivo .py e retorna seu resumo em Markdown."""
    try:
        conteudo = caminho_arquivo.read_text(encoding="utf-8")
        arvore = ast.parse(conteudo)
        
        analisador = AnalisadorAST()
        analisador.visit(arvore)
        
        resumo = f"### 📁 `{caminho_arquivo.name}`\n"
        if not analisador.resultado:
            resumo += "*Nenhuma classe ou função encontrada.*\n"
        else:
            resumo += "\n".join(analisador.resultado) + "\n"
        return resumo
        
    except SyntaxError:
        return f"### 📁 `{caminho_arquivo.name}`\n*Erro de sintaxe. Não foi possível mapear.*\n"
    except Exception as e:
        return f"### 📁 `{caminho_arquivo.name}`\n*Erro ao ler arquivo: {e}*\n"

def extrair_arquivos_py_do_gitignore(caminho_gitignore: Path) -> list:
    """
    Lê o .gitignore, encontra as inclusões explícitas (!) 
    e retorna os caminhos dos arquivos .py encontrados.
    """
    diretorio_projeto = caminho_gitignore.parent
    arquivos_py_encontrados = set() # Usamos set para evitar arquivos duplicados

    try:
        linhas = caminho_gitignore.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"Erro ao ler o arquivo .gitignore: {e}")
        sys.exit(1)

    for linha in linhas:
        linha = linha.strip()
        # Procura pelas regras de inclusão que não sejam apenas diretórios
        if linha.startswith('!') and not linha.endswith('/'):
            padrao = linha[1:] # Remove o '!' do início da string
            
            # O glob resolve tanto arquivos diretos (main.py) quanto curingas (*.py)
            for arquivo_encontrado in diretorio_projeto.glob(padrao):
                if arquivo_encontrado.is_file() and arquivo_encontrado.suffix == '.py':
                    arquivos_py_encontrados.add(arquivo_encontrado.resolve())

    # Retorna uma lista ordenada para o Markdown ficar sempre no mesmo padrão
    return sorted(list(arquivos_py_encontrados))

def gerar_mapa_repositorio(caminho_gitignore_str: str, arquivo_saida_str: str):
    """Orquestra a leitura do gitignore, mapeamento e geração do Markdown."""
    caminho_gitignore = Path(caminho_gitignore_str)
    
    if not caminho_gitignore.exists():
        print(f"Erro: O arquivo '{caminho_gitignore}' não foi encontrado.")
        sys.exit(1)

    print("🔍 Lendo regras do .gitignore...")
    arquivos_para_processar = extrair_arquivos_py_do_gitignore(caminho_gitignore)
    
    if not arquivos_para_processar:
        print("⚠️ Nenhum arquivo .py válido foi encontrado nas regras de inclusão (!) do seu .gitignore.")
        sys.exit(0)

    print(f"⚙️ Mapeando {len(arquivos_para_processar)} arquivos Python...")
    
    mapa_completo = ["# Resumo da Arquitetura do Projeto\n"]
    mapa_completo.append("*Este arquivo foi gerado automaticamente pelo PyResumidor com base no `.gitignore`.*\n")
    mapa_completo.append("---\n")
    
    for arquivo in arquivos_para_processar:
        resumo_arquivo = processar_arquivo_py(arquivo)
        mapa_completo.append(resumo_arquivo)
        mapa_completo.append("\n---\n")
        
    Path(arquivo_saida_str).write_text("\n".join(mapa_completo), encoding="utf-8")
    print(f"✅ Mapa gerado com sucesso em: {arquivo_saida_str}")

if __name__ == "__main__":
    # Configura o argparse para receber os dois parâmetros solicitados
    parser = argparse.ArgumentParser(description="Gera um resumo do código Python baseado no .gitignore.")
    parser.add_argument("gitignore_path", help="Caminho para o arquivo .gitignore do projeto alvo.")
    parser.add_argument("output_path", help="Caminho e nome do arquivo .md de saída (ex: resumo.md).")
    
    args = parser.parse_args()
    
    gerar_mapa_repositorio(args.gitignore_path, args.output_path)

# Como utilizar
# python gerar_mapa.py <CAMINHO_DO_GITIGNORE> <CAMINHO_DO_MARKDOWN_DE_SAIDA>

# Exemplo prático:
# python gerar_mapa.py ../MeuSuperProjeto/.gitignore ../MeuSuperProjeto/resumo_do_projeto.md