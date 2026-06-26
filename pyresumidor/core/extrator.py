import ast
import json
import re
import argparse
from pathlib import Path
from .resultados import ResultadoExtrair, ItemExtraido, ErroEntrada
import sys

try:
    # Reaproveita as instruções de formato do aplicador, para anexá-las ao fim
    # da saída e fechar o ciclo do pipeline (extrair -> aplicar) sem cópia manual.
    from .aplicador import INSTRUCOES_IA
except ImportError:
    INSTRUCOES_IA = None

try:
    from . import clipboard
except ImportError:
    clipboard = None

class ExtratorAST(ast.NodeVisitor):
    """Visitador AST responsável por localizar e extrair o código-fonte de classes, funções e métodos selecionados."""
    def __init__(self, source_code, alvos_classes, alvos_funcoes):
        self.source_code = source_code
        self.linhas_fonte = source_code.splitlines()
        self.alvos_classes = set(alvos_classes)
        # Separa alvos por nome simples (função de módulo / nome solto) dos alvos
        # em notação "Classe.metodo", que exigem casar o método dentro da classe
        # certa — não basta o nome do método bater em qualquer lugar.
        self.alvos_funcoes = set()
        self.alvos_metodos = {}  # nome_da_classe -> {nomes_de_metodos}
        for alvo in alvos_funcoes:
            if "." in alvo:
                classe, _, metodo = alvo.partition(".")
                self.alvos_metodos.setdefault(classe, set()).add(metodo)
            else:
                self.alvos_funcoes.add(alvo)
        self.codigo_extraido = []
        self._pilha_classes = []  # rastreia a classe que está sendo visitada

    def _fonte_do_no(self, no):
        """Código-fonte do nó INCLUINDO os decoradores, com a indentação do nível
        do nó removida (dedent) para leitura limpa.

        Diferente de ast.get_source_segment, que começa na linha do `def`/`class`
        e descarta os decoradores — informação que a IA precisa ver (ex.: @Slot,
        @property) para depois devolver a definição completa.
        """
        if getattr(no, "decorator_list", None):
            inicio = no.decorator_list[0].lineno  # 1-based
        else:
            inicio = no.lineno
        bloco = self.linhas_fonte[inicio - 1:no.end_lineno]
        # Remove a indentação comum (mínima entre as linhas não vazias).
        recuos = [len(l) - len(l.lstrip()) for l in bloco if l.strip()]
        corte = min(recuos) if recuos else 0
        return "\n".join(l[corte:] if l.strip() else "" for l in bloco)

    def visit_ClassDef(self, no):
        if no.name in self.alvos_classes:
            # Captura o código exato da classe inteira.
            self.codigo_extraido.append((no.name, "Classe", self._fonte_do_no(no)))
            # Se a classe inteira foi pedida, não duplicamos seus métodos.
            self.alvos_metodos.pop(no.name, None)
        # Empilha o nome para que os métodos do corpo saibam a que classe
        # pertencem; segue visitando para achar métodos pedidos via "Classe.metodo"
        # mesmo quando a classe inteira NÃO foi pedida.
        self._pilha_classes.append(no.name)
        self.generic_visit(no)
        self._pilha_classes.pop()

    def visit_FunctionDef(self, no):
        capturado = False
        # 1) Função/método pedido pelo nome simples (nível de módulo ou solto).
        if no.name in self.alvos_funcoes:
            self.codigo_extraido.append((no.name, "Função/Método", self._fonte_do_no(no)))
            capturado = True
        # 2) Método pedido como "Classe.metodo": só casa se estiver diretamente
        #    dentro da classe nomeada (a classe mais interna atual na pilha).
        if not capturado and self._pilha_classes:
            classe_atual = self._pilha_classes[-1]
            metodos = self.alvos_metodos.get(classe_atual)
            if metodos and no.name in metodos:
                nome_completo = f"{classe_atual}.{no.name}"
                self.codigo_extraido.append((nome_completo, "Método", self._fonte_do_no(no)))
        self.generic_visit(no)

    # Métodos/funções assíncronos (async def) usam a mesma lógica de casamento.
    visit_AsyncFunctionDef = visit_FunctionDef

def extrair_json_de_texto(texto: str) -> dict:
    """Procura e carrega o bloco JSON dentro de um texto (resposta da IA).

    Levanta ErroEntrada (sem sys.exit) quando não acha JSON ou ele é inválido —
    os pontos de entrada do core convertem isso em Resultado*(sucesso=False).
    """
    cb = chr(96) * 3
    texto = texto.strip()
    # 1. Tenta achar o bloco ```json ... ``` (padrão)
    match = re.search(r'```json\s*(.*?)\s*```', texto, re.DOTALL | re.IGNORECASE)
    bloco_json = ""
    if match:
        bloco_json = match.group(1)
    else:
        # 2. Fallback: primeiro '{' e último '}' do texto
        inicio = texto.find('{')
        fim = texto.rfind('}')
        if inicio != -1 and fim != -1:
            bloco_json = texto[inicio:fim + 1]
        else:
            raise ErroEntrada(
                f"Não encontrei chaves {{ }} nem um bloco {cb}json no texto da resposta.")
    try:
        return json.loads(bloco_json)
    except json.JSONDecodeError as e:
        raise ErroEntrada(f"Erro ao decodificar o JSON: {e} | Trecho: {bloco_json[:200]}")

def extrair_json_da_resposta(caminho_resposta: Path) -> dict:
    """Lê o arquivo da resposta e extrai o bloco JSON."""
    return extrair_json_de_texto(caminho_resposta.read_text(encoding="utf-8"))

def processar_arquivo(caminho_arquivo: Path, classes_alvo: list, funcoes_alvo: list):
    """Usa o AST para extrair apenas as partes solicitadas de um arquivo.

    Retorna (markdown, n_encontrados). O n_encontrados deixa o chamador saber, em
    nível de arquivo, quantos dos nós pedidos casaram — alimenta o resultado
    estruturado sem precisar raspar a string. (Quais nós casaram, individualmente,
    fica para quando o ExtratorAST reportar isso.)
    """
    cb = chr(96) * 3
    try:
        source_code = caminho_arquivo.read_text(encoding="utf-8")
        arvore = ast.parse(source_code)

        visitante = ExtratorAST(source_code, classes_alvo, funcoes_alvo)
        visitante.visit(arvore)

        if not visitante.codigo_extraido:
            return (f"⚠️ Nenhuma das classes/funções solicitadas foi encontrada em `{caminho_arquivo.name}`.\n", 0)

        resultado = ""
        for nome, tipo, codigo in visitante.codigo_extraido:
            resultado += f"\n#### {tipo}: `{nome}`\n{cb}python\n{codigo}\n{cb}\n"
        return (resultado, len(visitante.codigo_extraido))

    except Exception as e:
        return (f"⚠️ Erro ao processar `{caminho_arquivo.name}`: {e}\n", 0)

def _obter_texto_resposta(resposta_path_str: str, colar: bool) -> dict:
    """Decide a origem da resposta da IA: clipboard (--colar) ou arquivo, e devolve o JSON.

    Levanta ErroEntrada em falha (sem sys.exit).
    """
    if colar:
        if clipboard is None:
            raise ErroEntrada("clipboard indisponível; não dá para usar --colar.")
        try:
            texto = clipboard.colar()
        except clipboard.ClipboardIndisponivel as e:
            raise ErroEntrada(f"Não consegui ler a área de transferência: {e}")
        return extrair_json_de_texto(texto)

    resposta_path = Path(resposta_path_str).resolve()
    if not resposta_path.exists():
        raise ErroEntrada(f"Arquivo com a resposta da IA não encontrado ({resposta_path})")
    return extrair_json_da_resposta(resposta_path)

def executar_extracao(resposta_path_str: str, projeto_path_str: str, saida_path_str: str,
                      incluir_instrucoes: bool = True, colar: bool = False, copiar: bool = False):
    """Lê os requisitos da IA, extrai classes/funções e grava o Markdown de saída.

    Retorna ResultadoExtrair: não imprime nem encerra o processo.
    """
    cb = chr(96) * 3
    projeto_path = Path(projeto_path_str).resolve()

    try:
        requisicoes = _obter_texto_resposta(resposta_path_str, colar)
    except ErroEntrada as e:
        return ResultadoExtrair(sucesso=False, conteudo="", caminho_saida=None,
                                itens=[], total_linhas_extraidas=0,
                                instrucoes_anexadas=False, copiado=False, erros=[str(e)])

    md_saida = ["# Código Extraído para a IA\n\n"]
    itens = []
    avisos = []

    # 1. Arquivos completos (encontrado confiável: existe no disco)
    for caminho_relativo in requisicoes.get("arquivos_completos", []):
        arquivo_alvo = projeto_path / caminho_relativo
        md_saida.append(f"### 📄 Arquivo Completo: `{caminho_relativo}`\n")
        existe = arquivo_alvo.exists()
        if existe:
            codigo = arquivo_alvo.read_text(encoding="utf-8")
            md_saida.append(f"{cb}python\n{codigo}\n{cb}\n")
        else:
            md_saida.append("*⚠️ Arquivo não encontrado no projeto.*\n")
        md_saida.append("---\n")
        itens.append(ItemExtraido(caminho=caminho_relativo, tipo="arquivo", nome=None, encontrado=existe))

    # 2. Classes e funções
    dicionario_classes = requisicoes.get("classes", {})
    dicionario_funcoes = requisicoes.get("funcoes", {})
    todos_arquivos = set(list(dicionario_classes.keys()) + list(dicionario_funcoes.keys()))

    for caminho_relativo in todos_arquivos:
        arquivo_alvo = projeto_path / caminho_relativo
        md_saida.append(f"### ✂️ Trechos Extraídos: `{caminho_relativo}`")

        classes_alvo = dicionario_classes.get(caminho_relativo, [])
        funcoes_alvo = dicionario_funcoes.get(caminho_relativo, [])
        pedidos = [("classe", n) for n in classes_alvo] + [("funcao", n) for n in funcoes_alvo]

        if arquivo_alvo.exists():
            trechos, n_encontrados = processar_arquivo(arquivo_alvo, classes_alvo, funcoes_alvo)
            md_saida.append(trechos)
            # Honesto: só afirmamos "encontrado" por item quando TODOS casaram.
            todos_casaram = (n_encontrados > 0 and n_encontrados == len(pedidos))
            for tipo, nome in pedidos:
                itens.append(ItemExtraido(caminho=caminho_relativo, tipo=tipo, nome=nome, encontrado=todos_casaram))
            if 0 < n_encontrados < len(pedidos):
                avisos.append(f"{caminho_relativo}: {n_encontrados}/{len(pedidos)} item(ns) localizado(s); "
                              "ainda não dá para dizer individualmente quais (melhoria futura no extrator).")
        else:
            md_saida.append("\n*⚠️ Arquivo não encontrado no projeto.*\n")
            for tipo, nome in pedidos:
                itens.append(ItemExtraido(caminho=caminho_relativo, tipo=tipo, nome=nome, encontrado=False))
        md_saida.append("---\n")

    # 3. Instruções do aplicador
    instrucoes_anexadas = False
    if incluir_instrucoes:
        if INSTRUCOES_IA:
            md_saida.append("\n---\n")
            md_saida.append(INSTRUCOES_IA)
            instrucoes_anexadas = True
        else:
            avisos.append("INSTRUCOES_IA do aplicador indisponível; instruções NÃO anexadas.")

    conteudo = "\n".join(md_saida)
    # NB: total_linhas_extraidas = tamanho do md gerado (linhas de código por nó
    # ficam para quando o extrator reportar isso).
    total_linhas = len(conteudo.splitlines())

    try:
        Path(saida_path_str).write_text(conteudo, encoding="utf-8")
    except Exception as e:
        return ResultadoExtrair(sucesso=False, conteudo=conteudo, caminho_saida=None,
                                itens=itens, total_linhas_extraidas=total_linhas,
                                instrucoes_anexadas=instrucoes_anexadas, copiado=False,
                                erros=[f"Erro ao salvar a saída: {e}"], avisos=avisos)

    copiado = False
    if copiar:
        if clipboard is None:
            avisos.append("clipboard indisponível; --copiar ignorado.")
        else:
            try:
                clipboard.copiar(conteudo)
                copiado = True
            except clipboard.ClipboardIndisponivel as e:
                avisos.append(f"Não consegui copiar: {e}")

    return ResultadoExtrair(sucesso=True, conteudo=conteudo,
                            caminho_saida=str(Path(saida_path_str).resolve()),
                            itens=itens, total_linhas_extraidas=total_linhas,
                            instrucoes_anexadas=instrucoes_anexadas, copiado=copiado,
                            avisos=avisos)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai código-fonte baseado em um JSON da IA.")
    parser.add_argument("resposta_ia", nargs="?",
                        help="Arquivo txt/md com a resposta que a IA te deu. Opcional se usar --colar.")
    parser.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do seu projeto (ex: ../VisualizadorPN).")
    parser.add_argument("output_path", nargs="?", help="Caminho do arquivo .md de saída com os códigos extraídos.")
    parser.add_argument(
        "--sem-instrucoes",
        action="store_true",
        help="Não anexa ao fim da saída as instruções de formato do aplicador.py "
             "(plano + blocos de código).",
    )
    parser.add_argument(
        "--colar",
        action="store_true",
        help="Lê a resposta da IA da área de transferência em vez de um arquivo "
             "(assim você não passa 'resposta_ia').",
    )
    parser.add_argument(
        "--copiar",
        action="store_true",
        help="Copia a saída (código extraído) para a área de transferência, pronta para colar no chat.",
    )

    args = parser.parse_args()

    # Reorganiza os posicionais conforme --colar (com --colar não se passa resposta_ia).
    posicionais = [p for p in (args.resposta_ia, args.diretorio_projeto, args.output_path) if p is not None]
    if args.colar:
        if len(posicionais) != 2:
            parser.error("com --colar, informe apenas: diretorio_projeto e output_path.")
        args.resposta_ia = None
        args.diretorio_projeto, args.output_path = posicionais
    else:
        if len(posicionais) != 3:
            parser.error("informe: resposta_ia, diretorio_projeto e output_path "
                         "(ou use --colar passando só os 2 últimos).")
        args.resposta_ia, args.diretorio_projeto, args.output_path = posicionais

    executar_extracao(args.resposta_ia, args.diretorio_projeto, args.output_path,
                      incluir_instrucoes=not args.sem_instrucoes,
                      colar=args.colar, copiar=args.copiar)

# Como usar
# python .\extrator.py .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md
#
# Lendo a resposta da IA direto da área de transferência (sem salvar arquivo):
# python .\extrator.py --colar ..\VisualizadorPN .\test\codigo_para_ia.md
#
# Lendo do clipboard E copiando o resultado de volta pro clipboard (ciclo completo):
# python .\extrator.py --colar --copiar ..\VisualizadorPN .\test\codigo_para_ia.md
#
# Para gerar só o código, sem o guia de aplicação no fim:
# python .\extrator.py .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md --sem-instrucoes
