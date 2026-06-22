import ast
import re
import json
import argparse
import textwrap
import difflib
import shutil
from pathlib import Path
from collections import defaultdict
import sys

# Variáveis auxiliares para evitar que o renderizador de Markdown do chat
# quebre este arquivo em vários blocos de código quando copiado.
B3 = "`" * 3
B4 = "`" * 4

# ----------------------------------------------------------------------------
# Bloco de instruções para colar no chat com a IA (fase de implementação).
# Use `python aplicador.py --instrucoes` para imprimir isto no terminal.
# ----------------------------------------------------------------------------
INSTRUCOES_IA = f"""
# 🤖 INSTRUÇÕES PARA GERAR ALTERAÇÕES (aplicador.py)

Quando o usuário pedir para implementar a solução, NÃO escreva diffs nem números
de linha. Em vez disso, devolva o CÓDIGO NOVO completo de cada função/classe que
deve mudar. Um script de aplicação localiza o alvo pelo NOME (via AST) e faz a
substituição, então você nunca precisa se preocupar com posições no arquivo.

Sua resposta deve conter DUAS partes:

1) Um bloco {B4}json com o PLANO de operações.
2) UM ÚNICO bloco de código contendo todas as operações, separadas por um comentário de ID.

## 1. Plano (bloco {B4}json)

{B4}json
{{
  "operacoes": [
    {{"acao": "substituir", "arquivo": "src/core.py", "tipo": "funcao", "alvo": "processa", "codigo_id": "b1"}},
    {{"acao": "substituir", "arquivo": "src/core.py", "tipo": "classe", "alvo": "Motor",    "codigo_id": "b2"}},
    {{"acao": "substituir", "arquivo": "src/core.py", "tipo": "metodo", "alvo": "Motor.run", "codigo_id": "b3"}},
    {{"acao": "adicionar",  "arquivo": "src/core.py", "tipo": "funcao", "alvo": "nova_func", "codigo_id": "b4"}},
    {{"acao": "adicionar",  "arquivo": "src/core.py", "tipo": "metodo", "alvo": "Motor.reset", "codigo_id": "b5"}},
    {{"acao": "trecho",     "arquivo": "src/core.py", "tipo": "metodo", "alvo": "Motor.run", "posicao": "substituir", "ancora_id": "a1", "codigo_id": "b6"}},
    {{"acao": "trecho",     "arquivo": "config.yaml", "tipo": "arquivo", "posicao": "depois", "ancora_id": "a2", "codigo_id": "b7"}},
    {{"acao": "arquivo",    "arquivo": "config.yaml", "codigo_id": "b8"}}
  ]
}}
{B4}

## 2. Bloco de código ÚNICO

Coloque todos os trechos de código (E as âncoras) em um ÚNICO bloco. Antes de cada
função, classe, arquivo ou âncora, adicione um comentário separador EXATAMENTE neste
formato: `# --- id=<id> ---`

{B3}python
# --- id=b1 ---
def processa(self, dados):
    return dados * 2

# --- id=b2 ---
class Motor:
    pass

# --- id=b3 ---
def run(self):
    print("running")

# --- id=a1 ---
contador = 0

# --- id=b6 ---
contador = 1
{B3}

## 3. Edições cirúrgicas por âncora (acao "trecho")

Use "trecho" quando precisar mexer em POUCAS LINHAS dentro de um nó (ou de um arquivo)
sem reescrever a função/classe inteira. Em vez de contar linhas, você fornece:

- uma ÂNCORA (`ancora_id`): um pedaço EXISTENTE do código, copiado como está hoje,
  que serve de ponto de referência;
- um código novo (`codigo_id`): o que entra em relação à âncora.

O script busca a âncora APENAS dentro do escopo indicado por `tipo`/`alvo` (o span do
nó), o que evita ambiguidade. A âncora precisa casar EXATAMENTE UMA vez nesse escopo;
se casar zero ou duas+ vezes, nada é gravado e você recebe um erro pedindo uma âncora
mais específica.

`posicao` controla o que acontece com a âncora:
- "substituir": troca as linhas da âncora pelo código novo (use um bloco vazio em
  `codigo_id`, ou omita `codigo_id`, para APAGAR as linhas da âncora);
- "antes": insere o código novo imediatamente ANTES da âncora;
- "depois": insere o código novo imediatamente DEPOIS da âncora.

Para ancorar dentro de um arquivo não-Python (config), use `"tipo": "arquivo"`: aí a
busca da âncora cobre o arquivo inteiro (não há nó AST para delimitar).

## Regras
1. `acao`: "substituir" (nó existente), "adicionar" (nó novo), "trecho" (edição por
   âncora) ou "arquivo" (substitui/cria o arquivo inteiro — use para configs e
   arquivos novos).
2. `tipo`: "funcao", "classe", "metodo" ou "arquivo". Para "metodo", o `alvo` DEVE ser
   "NomeDaClasse.nome_do_metodo" — vale para "substituir"/"adicionar"/"trecho".
   "adicionar" com tipo "funcao"/"classe" insere no nível do módulo. Em "trecho",
   "arquivo" usa o arquivo inteiro como escopo de busca da âncora.
3. Entregue SEMPRE a definição completa (incluindo decoradores) em "substituir"/"adicionar".
4. Não se preocupe com indentação: o script re-indenta para a coluna correta. Em "trecho",
   o código novo herda a indentação da primeira linha da âncora.
5. Cada `codigo_id`/`ancora_id` do plano deve ter um `# --- id=... ---` correspondente
   no bloco de código.
6. Não inclua números de linha, diffs ou contexto ao redor — só o código novo.
7. A âncora de "trecho" deve ser copiada IGUALZINHO ao código atual (a comparação ignora
   indentação e espaços à direita, mas o conteúdo precisa bater). Prefira âncoras curtas
   e únicas dentro do escopo (1 a 3 linhas costuma bastar).
8. Em "trecho" com "posicao": "antes"/"depois", o `codigo_id` é obrigatório e não pode
   ser vazio.
"""


def carregar_plano(texto: str) -> dict:
    """Extrai o bloco json com o plano de operações da resposta da IA."""
    # Tenta achar o bloco com 4 crases
    match = re.search(rf'{B4}json\s*(.*?)\s*{B4}', texto, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback para 3 crases
        match = re.search(rf'{B3}json\s*(.*?)\s*{B3}', texto, re.DOTALL | re.IGNORECASE)

    if match:
        bloco = match.group(1)
    else:
        inicio, fim = texto.find('{'), texto.rfind('}')
        if inicio != -1 and fim != -1:
            bloco = texto[inicio:fim + 1]
        else:
            print(f"❌ Não encontrei um bloco {B4}json (plano) na resposta da IA.")
            sys.exit(1)
    try:
        return json.loads(bloco)
    except json.JSONDecodeError as e:
        print(f"❌ Erro ao decodificar o JSON do plano: {e}")
        print(f"Trecho:\n{bloco[:200]}...")
        sys.exit(1)


def indexar_blocos_codigo(texto: str) -> dict:
    """
    Localiza comentários no formato `# --- id=<algo> ---` e mapeia
    para o código que vem logo abaixo dele, até o próximo ID ou fim do texto.
    """
    blocos = {}
    padrao_id = re.compile(r'^#\s*---\s*id=([a-zA-Z0-9_]+)\s*---$', re.MULTILINE)
    matches = list(padrao_id.finditer(texto))

    for i, match in enumerate(matches):
        codigo_id = match.group(1)
        inicio_codigo = match.end()

        if i + 1 < len(matches):
            fim_codigo = matches[i + 1].start()
        else:
            fim_codigo = len(texto)

        codigo_bruto = texto[inicio_codigo:fim_codigo]

        # Limpa possíveis crases de fechamento de markdown (```) que
        # possam existir ao final do último bloco de código.
        # Usa regex com 1 crase avaliada para não quebrar a UI
        codigo_limpo = re.sub(r'^`{3,}.*$', '', codigo_bruto, flags=re.MULTILINE).strip()
        blocos[codigo_id] = codigo_limpo

    return blocos


def _encontrar_no(arvore: ast.Module, tipo: str, alvo: str):
    """Localiza o nó AST alvo no nível pedido. Retorna o nó ou None."""
    funcdefs = (ast.FunctionDef, ast.AsyncFunctionDef)

    if tipo == "funcao":
        for no in arvore.body:
            if isinstance(no, funcdefs) and no.name == alvo:
                return no

    elif tipo == "classe":
        for no in arvore.body:
            if isinstance(no, ast.ClassDef) and no.name == alvo:
                return no

    elif tipo == "metodo":
        if "." not in alvo:
            return None  # exige "Classe.metodo"
        nome_classe, nome_metodo = alvo.split(".", 1)
        for no in arvore.body:
            if isinstance(no, ast.ClassDef) and no.name == nome_classe:
                for sub in no.body:
                    if isinstance(sub, funcdefs) and sub.name == nome_metodo:
                        return sub
    return None


def _encontrar_classe(arvore: ast.Module, nome_classe: str):
    """Localiza uma ClassDef no nível do módulo. Retorna o nó ou None."""
    for no in arvore.body:
        if isinstance(no, ast.ClassDef) and no.name == nome_classe:
            return no
    return None


def _span_do_no(no) -> tuple:
    """Intervalo de linhas (1-based, inclusivo) ocupado pelo nó, contando decoradores."""
    inicio = no.lineno
    decoradores = getattr(no, "decorator_list", None)
    if decoradores:
        inicio = min([inicio] + [d.lineno for d in decoradores])
    return inicio, no.end_lineno


def _reindentar(codigo: str, col_offset: int) -> str:
    """Remove a indentação que a IA mandou e re-aplica a coluna do nó original."""
    corpo = textwrap.dedent(codigo).strip("\n")
    indent = " " * col_offset
    linhas = [(indent + ln) if ln.strip() else "" for ln in corpo.split("\n")]
    return "\n".join(linhas)


def _normalizar_bloco(linhas: list) -> list:
    """Dedenta o bloco como unidade e remove espaços à direita de cada linha.

    Preserva a indentação RELATIVA (que importa em Python), mas ignora a coluna
    absoluta e o trailing whitespace, para que a âncora da IA case mesmo quando ela
    erra a indentação ou os espaços do fim.
    """
    return [ln.rstrip() for ln in textwrap.dedent("\n".join(linhas)).split("\n")]


def _aplicar_trecho_no_texto(fonte: str, no, ancora: str, codigo: str, posicao: str):
    """Substitui/insere código relativo a uma âncora textual, restrita ao escopo.

    `no` é o nó AST que delimita a janela de busca; se `no` for None, a janela é o
    arquivo inteiro (caso de configs não-Python). A âncora precisa casar exatamente
    uma vez dentro da janela. Retorna (nova_fonte, erro_ou_None).
    """
    linhas = fonte.splitlines()

    if no is None:
        win_ini, win_fim = 0, len(linhas)  # janela = arquivo inteiro (0-based, exclusivo)
    else:
        ini, fim = _span_do_no(no)          # 1-based inclusivo
        win_ini, win_fim = ini - 1, fim

    # Normaliza a âncora e descarta linhas em branco no começo/fim.
    anc = [ln.rstrip() for ln in textwrap.dedent(ancora).strip("\n").split("\n")]
    while anc and not anc[0].strip():
        anc.pop(0)
    while anc and not anc[-1].strip():
        anc.pop()
    if not anc:
        return fonte, "âncora vazia após normalização."

    anc_norm = _normalizar_bloco(anc)
    n = len(anc_norm)

    matches = []
    for i in range(win_ini, win_fim - n + 1):
        if _normalizar_bloco(linhas[i:i + n]) == anc_norm:
            matches.append(i)

    if len(matches) == 0:
        return fonte, "âncora não encontrada dentro do escopo do alvo."
    if len(matches) > 1:
        return fonte, (f"âncora ambígua: {len(matches)} ocorrências no escopo do alvo; "
                       "torne a âncora mais específica.")

    m = matches[0]
    primeira = linhas[m]
    col = len(primeira) - len(primeira.lstrip())

    if codigo and codigo.strip():
        novo_codigo = _reindentar(codigo, col).split("\n")
    else:
        novo_codigo = []  # apagar (substituir por nada)

    if posicao == "substituir":
        novas = linhas[:m] + novo_codigo + linhas[m + n:]
    elif posicao == "antes":
        novas = linhas[:m] + novo_codigo + linhas[m:]
    elif posicao == "depois":
        novas = linhas[:m + n] + novo_codigo + linhas[m + n:]
    else:
        return fonte, f"posição inválida: '{posicao}' (use 'substituir', 'antes' ou 'depois')."

    return "\n".join(novas), None


def _substituir_no_texto(fonte: str, no, codigo_novo: str) -> str:
    inicio, fim = _span_do_no(no)
    linhas = fonte.splitlines()
    novo = _reindentar(codigo_novo, no.col_offset)
    novas = linhas[:inicio - 1] + novo.split("\n") + linhas[fim:]
    return "\n".join(novas)


def _adicionar_no_texto(fonte: str, codigo_novo: str) -> str:
    corpo = textwrap.dedent(codigo_novo).strip("\n")
    base = fonte.rstrip("\n")
    if base:
        return base + "\n\n\n" + corpo + "\n"
    return corpo + "\n"


def _adicionar_metodo_no_texto(fonte: str, classe_no, codigo_novo: str) -> str:
    """Insere um método novo no fim do corpo da classe, com a indentação correta."""
    # Indentação dos membros da classe (4 p/ classe de topo, 8 p/ classe aninhada...).
    body_indent = classe_no.body[0].col_offset
    # Última linha ocupada pelo último membro do corpo da classe (1-based).
    pos_fim = classe_no.body[-1].end_lineno
    novo_metodo = _reindentar(codigo_novo, body_indent)
    linhas = fonte.splitlines()
    insercao = [""] + novo_metodo.split("\n")  # 1 linha em branco de separação (PEP8)
    novas = linhas[:pos_fim] + insercao + linhas[pos_fim:]
    return "\n".join(novas)


def _gerar_diff(rel: str, original: str, novo: str) -> str:
    """Diff unificado estilo git (aceito por `git apply`)."""
    a = original if (original == "" or original.endswith("\n")) else original + "\n"
    b = novo if novo.endswith("\n") else novo + "\n"
    if a == b:
        return ""
    linhas = difflib.unified_diff(
        a.splitlines(keepends=True),
        b.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    corpo = "".join(linhas)
    if not corpo:
        return ""
    return f"diff --git a/{rel} b/{rel}\n" + corpo


def aplicar_em_arquivo(rel: str, alvo: Path, ops: list, blocos: dict) -> tuple:
    """Aplica (em memória) todas as operações de um arquivo.

    Retorna (texto_original, texto_novo, lista_de_erros).
    """
    erros = []
    original = alvo.read_text(encoding="utf-8", errors="replace") if alvo.exists() else ""
    novo = original

    for op in ops:
        acao = op.get("acao")
        codigo_id = op.get("codigo_id")
        codigo = blocos.get(codigo_id) if codigo_id else None

        if acao == "arquivo":
            if codigo is None:
                erros.append(f"[{rel}] bloco de código '{codigo_id}' não encontrado.")
                continue
            novo = textwrap.dedent(codigo).strip("\n") + "\n"
            continue

        if acao == "trecho":
            tipo = op.get("tipo")
            alvo_nome = op.get("alvo", "")
            posicao = op.get("posicao", "substituir")
            ancora_id = op.get("ancora_id")
            ancora = blocos.get(ancora_id) if ancora_id else None

            if posicao not in ("substituir", "antes", "depois"):
                erros.append(f"[{rel}] posição inválida em 'trecho': '{posicao}'.")
                continue
            if not ancora or not ancora.strip():
                erros.append(f"[{rel}] âncora '{ancora_id}' não encontrada ou vazia.")
                continue
            # codigo_id é opcional só no caso de apagar (substituir por nada).
            if codigo_id is not None and codigo is None:
                erros.append(f"[{rel}] bloco de código '{codigo_id}' não encontrado.")
                continue
            if posicao in ("antes", "depois") and not (codigo and codigo.strip()):
                erros.append(f"[{rel}] 'trecho' com posição '{posicao}' exige um código não-vazio.")
                continue

            if tipo == "arquivo":
                no = None  # escopo = arquivo inteiro
            else:
                if alvo.suffix != ".py":
                    erros.append(f"[{rel}] 'trecho' com tipo '{tipo}' exige arquivo .py; "
                                 "para configs use \"tipo\": \"arquivo\".")
                    continue
                try:
                    arvore = ast.parse(novo)
                except SyntaxError as e:
                    erros.append(f"[{rel}] não consegui parsear o estado atual do arquivo: {e}")
                    return original, original, erros
                no = _encontrar_no(arvore, tipo, alvo_nome)
                if no is None:
                    erros.append(f"[{rel}] {tipo} '{alvo_nome}' não encontrado para ancorar o trecho.")
                    continue

            resultado, erro = _aplicar_trecho_no_texto(novo, no, ancora, codigo or "", posicao)
            if erro:
                erros.append(f"[{rel}] {tipo} '{alvo_nome or rel}': {erro}")
                continue
            novo = resultado
            continue

        # Operações que dependem de AST exigem .py
        if alvo.suffix != ".py":
            erros.append(f"[{rel}] ação '{acao}' em arquivo não-Python; use \"acao\": \"arquivo\".")
            continue

        try:
            arvore = ast.parse(novo)
        except SyntaxError as e:
            erros.append(f"[{rel}] não consegui parsear o estado atual do arquivo: {e}")
            return original, original, erros

        tipo = op.get("tipo")
        alvo_nome = op.get("alvo", "")
        no = _encontrar_no(arvore, tipo, alvo_nome)

        if acao == "substituir":
            if no is None:
                erros.append(f"[{rel}] {tipo} '{alvo_nome}' não encontrado para substituir.")
                continue
            if codigo is None:
                erros.append(f"[{rel}] bloco de código '{codigo_id}' não encontrado.")
                continue
            novo = _substituir_no_texto(novo, no, codigo)

        elif acao == "adicionar":
            if codigo is None:
                erros.append(f"[{rel}] bloco de código '{codigo_id}' não encontrado.")
                continue
            if tipo == "metodo":
                if "." not in alvo_nome:
                    erros.append(f"[{rel}] para adicionar método use \"alvo\": \"Classe.metodo\".")
                    continue
                nome_classe, _ = alvo_nome.split(".", 1)
                classe_no = _encontrar_classe(arvore, nome_classe)
                if classe_no is None:
                    erros.append(f"[{rel}] classe '{nome_classe}' não encontrada para inserir o método.")
                    continue
                if no is not None:  # _encontrar_no já achou o método -> existe
                    erros.append(f"[{rel}] método '{alvo_nome}' já existe; use \"substituir\".")
                    continue
                novo = _adicionar_metodo_no_texto(novo, classe_no, codigo)
            else:
                if no is not None:
                    erros.append(f"[{rel}] {tipo} '{alvo_nome}' já existe; use \"substituir\".")
                    continue
                novo = _adicionar_no_texto(novo, codigo)

        else:
            erros.append(f"[{rel}] ação desconhecida: '{acao}'.")

    # Guarda-corpo: nunca devolve um .py que não parseia.
    if alvo.suffix == ".py" and novo != original:
        try:
            ast.parse(novo)
        except SyntaxError as e:
            erros.append(f"[{rel}] resultado final ficou com sintaxe inválida; arquivo NÃO será alterado: {e}")
            return original, original, erros

    return original, novo, erros


def executar(resposta_path_str: str, projeto_path_str: str,
             aplicar: bool, diff_path_str: str, sem_backup: bool):
    resposta_path = Path(resposta_path_str).resolve()
    projeto_path = Path(projeto_path_str).resolve()

    if not resposta_path.exists():
        print(f"❌ Arquivo com a resposta da IA não encontrado: {resposta_path}")
        sys.exit(1)

    texto = resposta_path.read_text(encoding="utf-8", errors="replace")
    plano = carregar_plano(texto)
    blocos = indexar_blocos_codigo(texto)
    operacoes = plano.get("operacoes", [])

    if not operacoes:
        print("⚠️ Nenhuma operação encontrada no plano (chave 'operacoes' vazia).")
        sys.exit(0)

    print(f"🔧 {len(operacoes)} operação(ões) no plano · {len(blocos)} bloco(s) de código encontrados.")
    print(f"📂 Projeto: {projeto_path}")
    print(f"{'✍️  MODO APLICAR (vai gravar)' if aplicar else '👀 MODO DRY-RUN (nada será gravado)'}\n")

    por_arquivo = defaultdict(list)
    for op in operacoes:
        rel = op.get("arquivo")
        if not rel:
            print("⚠️ Operação sem 'arquivo' — ignorada.")
            continue
        por_arquivo[rel].append(op)

    todos_diffs = []
    total_erros = []

    for rel, ops in por_arquivo.items():
        alvo = projeto_path / rel
        original, novo, erros = aplicar_em_arquivo(rel, alvo, ops, blocos)
        total_erros.extend(erros)

        diff = _gerar_diff(rel, original, novo)
        if diff:
            todos_diffs.append(diff)
            print(f"📝 {rel}")
            print(diff)
            if aplicar:
                if alvo.exists() and not sem_backup:
                    shutil.copy2(alvo, alvo.with_suffix(alvo.suffix + ".bak"))
                alvo.parent.mkdir(parents=True, exist_ok=True)
                conteudo = novo if novo.endswith("\n") else novo + "\n"
                alvo.write_text(conteudo, encoding="utf-8")
                print(f"   ✅ gravado{'' if sem_backup else ' (backup .bak criado)'}\n")
            else:
                print()
        else:
            print(f"➖ {rel}: nenhuma mudança gerada.\n")

    if diff_path_str and todos_diffs:
        Path(diff_path_str).write_text("\n".join(todos_diffs) + "\n", encoding="utf-8")
        print(f"💾 Patch combinado salvo em: {diff_path_str}")
        print(f"   Aplicar com Git:  git apply {diff_path_str}")
        print(f"   Conferir antes:   git apply --check {diff_path_str}")

    if total_erros:
        print("\n⚠️ Avisos/erros:")
        for e in total_erros:
            print(f"   - {e}")

    if not aplicar and todos_diffs:
        print("\nℹ️ Isto foi um dry-run. Use --aplicar para gravar, ou --diff arquivo.patch para salvar o patch.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aplica alterações da IA substituindo nós (funções/classes) por nome via AST."
    )
    parser.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta da IA (plano + blocos de código).")
    parser.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto (ex: ../VisualizadorPN).")
    parser.add_argument("--aplicar", action="store_true", help="Grava as alterações nos arquivos (default: dry-run).")
    parser.add_argument("--diff", dest="diff_path", default=None, help="Salva o patch unificado combinado neste caminho.")
    parser.add_argument("--sem-backup", action="store_true", help="Não cria arquivos .bak ao gravar.")
    parser.add_argument("--instrucoes", action="store_true", help="Imprime as instruções para colar no chat com a IA e sai.")

    args = parser.parse_args()

    if args.instrucoes:
        print(INSTRUCOES_IA)
        sys.exit(0)

    if not args.resposta_ia or not args.diretorio_projeto:
        parser.error("são necessários 'resposta_ia' e 'diretorio_projeto' (ou use --instrucoes).")

    executar(args.resposta_ia, args.diretorio_projeto, args.aplicar, args.diff_path, args.sem_backup)

# Como usar
# 1) Ver o que mudaria (dry-run, não grava nada):
#    python aplicador.py .\test\resposta.md ..\VisualizadorPN
#    python .\aplicador.py .\test\aplicador_in.md ..\VisualizadorPN
#
# 2) Salvar um patch para revisar/aplicar com Git:
#    python aplicador.py .\test\resposta.md ..\VisualizadorPN --diff .\test\mudancas.patch
#    git apply --check .\test\mudancas.patch
#    git apply .\test\mudancas.patch
#
# 3) Gravar direto nos arquivos (cria .bak por padrão):
#    python aplicador.py .\test\resposta.md ..\VisualizadorPN --aplicar
#    python .\aplicador.py .\test\aplicador_in.md ..\VisualizadorPN --aplicar
#
# 4) Ver as instruções para colar no chat com a IA:
#    python aplicador.py --instrucoes