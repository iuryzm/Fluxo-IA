import ast
import json
import re
import argparse
from pathlib import Path
import sys

# Garante que o diretório deste script esteja no sys.path, para conseguir importar
# o aplicador.py que fica ao lado dele (independente de onde o comando foi rodado).
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    # Reaproveita as instruções de formato do aplicador, para anexá-las ao fim
    # da saída e fechar o ciclo do pipeline (extrair -> aplicar) sem cópia manual.
    from aplicador import INSTRUCOES_IA
except ImportError:
    INSTRUCOES_IA = None

class ExtratorAST(ast.NodeVisitor):
    def __init__(self, source_code, alvos_classes, alvos_funcoes):
        self.source_code = source_code
        self.alvos_classes = set(alvos_classes)
        self.alvos_funcoes = set(alvos_funcoes)
        self.codigo_extraido = []

    def visit_ClassDef(self, no):
        if no.name in self.alvos_classes:
            # Captura o código exato da classe inteira
            codigo = ast.get_source_segment(self.source_code, no)
            self.codigo_extraido.append((no.name, "Classe", codigo))
        # Continua visitando para caso a IA tenha pedido uma função específica dentro de uma classe
        # que ela NÃO pediu inteira.
        self.generic_visit(no)

    def visit_FunctionDef(self, no):
        if no.name in self.alvos_funcoes:
            # Captura o código exato da função/método
            codigo = ast.get_source_segment(self.source_code, no)
            self.codigo_extraido.append((no.name, "Função/Método", codigo))
        self.generic_visit(no)

def extrair_json_da_resposta(caminho_resposta: Path) -> dict:
    """Procura e carrega o bloco JSON dentro do texto da IA."""
    texto = caminho_resposta.read_text(encoding="utf-8").strip()
    
    # 1. Tenta achar o bloco ```json ... ``` (Padrão)
    match = re.search(r'```json\s*(.*?)\s*```', texto, re.DOTALL | re.IGNORECASE)
    
    bloco_json = ""
    if match:
        bloco_json = match.group(1)
    else:
        # 2. Fallback: Procura o primeiro '{' e o último '}' no texto
        inicio = texto.find('{')
        fim = texto.rfind('}')
        if inicio != -1 and fim != -1:
            bloco_json = texto[inicio:fim+1]
        else:
            print("❌ Erro: Não foi possível encontrar chaves { } ou o bloco ```json no arquivo de resposta.")
            sys.exit(1)
            
    try:
        return json.loads(bloco_json)
    except json.JSONDecodeError as e:
        print(f"❌ Erro ao decodificar o JSON: {e}")
        print(f"Trecho capturado que gerou erro:\n{bloco_json[:200]}...")
        sys.exit(1)

def processar_arquivo(caminho_arquivo: Path, classes_alvo: list, funcoes_alvo: list) -> str:
    """Usa o AST para extrair apenas as partes solicitadas de um arquivo."""
    try:
        source_code = caminho_arquivo.read_text(encoding="utf-8")
        arvore = ast.parse(source_code)
        
        visitante = ExtratorAST(source_code, classes_alvo, funcoes_alvo)
        visitante.visit(arvore)
        
        if not visitante.codigo_extraido:
            return f"⚠️ Nenhuma das classes/funções solicitadas foi encontrada em `{caminho_arquivo.name}`.\n"
            
        resultado = ""
        for nome, tipo, codigo in visitante.codigo_extraido:
            resultado += f"\n#### {tipo}: `{nome}`\n```python\n{codigo}\n```\n"
        return resultado

    except Exception as e:
        return f"⚠️ Erro ao processar `{caminho_arquivo.name}`: {e}\n"

def executar_extracao(resposta_path_str: str, projeto_path_str: str, saida_path_str: str,
                      incluir_instrucoes: bool = True):
    resposta_path = Path(resposta_path_str).resolve()
    projeto_path = Path(projeto_path_str).resolve()
    
    if not resposta_path.exists():
        print(f"Erro: Arquivo com a resposta da IA não encontrado ({resposta_path})")
        sys.exit(1)
        
    print("🔍 Lendo as requisições da IA...")
    requisicoes = extrair_json_da_resposta(resposta_path)
    
    md_saida = ["# Código Extraído para a IA\n\n"]
    
    # 1. Arquivos Completos
    arquivos_completos = requisicoes.get("arquivos_completos", [])
    for caminho_relativo in arquivos_completos:
        arquivo_alvo = projeto_path / caminho_relativo
        md_saida.append(f"### 📄 Arquivo Completo: `{caminho_relativo}`\n")
        if arquivo_alvo.exists():
            codigo = arquivo_alvo.read_text(encoding="utf-8")
            md_saida.append(f"```python\n{codigo}\n```\n")
        else:
            md_saida.append(f"*⚠️ Arquivo não encontrado no projeto.*\n")
        md_saida.append("---\n")
            
    # 2. Classes e Funções
    dicionario_classes = requisicoes.get("classes", {})
    dicionario_funcoes = requisicoes.get("funcoes", {})
    
    # Junta todos os caminhos de arquivos que precisamos abrir
    todos_arquivos = set(list(dicionario_classes.keys()) + list(dicionario_funcoes.keys()))
    
    for caminho_relativo in todos_arquivos:
        arquivo_alvo = projeto_path / caminho_relativo
        md_saida.append(f"### ✂️ Trechos Extraídos: `{caminho_relativo}`")
        
        if arquivo_alvo.exists():
            classes_alvo = dicionario_classes.get(caminho_relativo, [])
            funcoes_alvo = dicionario_funcoes.get(caminho_relativo, [])
            
            trechos = processar_arquivo(arquivo_alvo, classes_alvo, funcoes_alvo)
            md_saida.append(trechos)
        else:
            md_saida.append(f"\n*⚠️ Arquivo não encontrado no projeto.*\n")
        md_saida.append("---\n")

    # 3. Instruções para a próxima resposta da IA (consumida pelo aplicador.py).
    # Anexa o guia de formato (plano + blocos de código) ao fim da saída, para que
    # a IA já saiba como devolver a solução sem você rodar `aplicador.py --instrucoes`.
    if incluir_instrucoes:
        if INSTRUCOES_IA:
            md_saida.append("\n---\n")
            md_saida.append(INSTRUCOES_IA)
        else:
            print("⚠️ Não encontrei o aplicador.py ao lado do extrator.py; as instruções "
                  "de aplicação NÃO foram anexadas. Use --sem-instrucoes para silenciar este aviso.")

    Path(saida_path_str).write_text("\n".join(md_saida), encoding="utf-8")
    sufixo = " (com instruções do aplicador anexadas)" if (incluir_instrucoes and INSTRUCOES_IA) else ""
    print(f"✅ Extração concluída! Arquivo gerado em: {saida_path_str}{sufixo}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai código-fonte baseado em um JSON da IA.")
    parser.add_argument("resposta_ia", help="Caminho do arquivo txt/md com a resposta que a IA te deu.")
    parser.add_argument("diretorio_projeto", help="Caminho raiz do seu projeto (ex: ../VisualizadorPN).")
    parser.add_argument("output_path", help="Caminho do arquivo .md de saída com os códigos extraídos.")
    parser.add_argument(
        "--sem-instrucoes",
        action="store_true",
        help="Não anexa ao fim da saída as instruções de formato do aplicador.py "
             "(plano + blocos de código).",
    )
    
    args = parser.parse_args()
    executar_extracao(args.resposta_ia, args.diretorio_projeto, args.output_path,
                      incluir_instrucoes=not args.sem_instrucoes)

# Como usar
# python .\extrator.py .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md
# python .\extrator.py .\test\extrator_in.json ..\VisualizadorPN .\test\extrator_out.md
#
# Para gerar só o código, sem o guia de aplicação no fim:
# python .\extrator.py .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md --sem-instrucoes