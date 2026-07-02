import ast
import re
import json
import argparse
import textwrap
import difflib
import shutil
from pathlib import Path
from .resultados import ResultadoAplicar, ResultadoArquivoAplicado, ErroEntrada, PassoComando, ResultadoComando, PassoPlano
from collections import defaultdict
import sys
import html
import tempfile
import webbrowser

# O clipboard é opcional: sem ele, --colar apenas avisa que não está disponível.
try:
    from . import clipboard
except ImportError:
    clipboard = None

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
    {{"acao": "adicionar_import", "arquivo": "src/core.py", "modulo": "os.path", "nomes": ["join", "exists"]}},
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
4. Em "substituir"/"adicionar" (nó inteiro), não se preocupe com indentação: o script
   re-indenta para a coluna correta do nó. Em "trecho" é WYSIWYG: escreva a âncora na
   indentação REAL que ela tem no arquivo (regra 7) e escreva o código novo na coluna
   em que ele deve ficar no resultado final. O script preserva a indentação relativa que
   você escrever e corrige apenas o desencontro entre a coluna que você deu à âncora e
   a real. Ex.: para inserir funções de nível de módulo depois de uma âncora que está
   DENTRO de uma função, escreva a âncora indentada (como no arquivo) e as funções
   novas na coluna 0.
5. Cada `codigo_id`/`ancora_id` do plano deve ter um `# --- id=... ---` correspondente
   no bloco de código.
6. Não inclua números de linha, diffs ou contexto ao redor — só o código novo.
7. A âncora de "trecho" deve ser copiada IGUALZINHO ao código atual, INCLUSIVE a
   indentação real. A busca ignora indentação/espaços para CASAR, mas a coluna que
   você escreve na âncora é a referência para posicionar o código novo — então copie a
   coluna de verdade. Prefira âncoras curtas e únicas no escopo (1 a 3 linhas).
   A âncora vem SEMPRE do CÓDIGO EXTRAÍDO que você recebeu (a saída do extrair),
   copiada byte a byte — NUNCA do MAPA. No mapa, a linha `**Dependências:**` é um
   resumo com perdas: mostra só os 5 primeiros imports, achatados numa única linha
   sem parênteses nem vírgulas de fim, e as assinaturas são reconstruídas sem `self`
   nem tipos. Esse texto quase nunca existe igual no disco, então ancorar nele falha
   silenciosamente. Na dúvida sobre a forma exata de um import multilinha, peça o
   arquivo via `"arquivos_completos"` e copie a âncora de lá.
8. Em "trecho" com "posicao": "antes"/"depois", o `codigo_id` é obrigatório e não pode
   ser vazio.
9. Para ADICIONAR NOMES a um import (`from X import ...`), use SEMPRE a ação
   dedicada `"adicionar_import"` — NUNCA `"trecho"`. Ela não usa âncora nem
   `codigo_id`: você informa o módulo e a lista de nomes direto no plano, e o
   script encontra o import via AST e insere os nomes que faltam, imune ao formato
   do import no disco (linha única ou multilinha entre parênteses) — que é
   justamente onde `"trecho"` falha com imports. Forma:
   {{"acao": "adicionar_import", "arquivo": "x.py", "modulo": "pacote.modulo", "nomes": ["NOME_A", "NOME_B"]}}
   Nomes devem ser identificadores simples (sem `as`, sem `.`). Para REMOVER nomes,
   trocar aliases ou mexer em `import X`/imports relativos, continue usando `"trecho"`.
"""


def carregar_plano(texto: str) -> dict:
    """Extrai o bloco json com o plano de operações da resposta da IA.

    Levanta ErroEntrada em falha (sem sys.exit).
    """
    match = re.search(rf'{B4}json\s*(.*?)\s*{B4}', texto, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(rf'{B3}json\s*(.*?)\s*{B3}', texto, re.DOTALL | re.IGNORECASE)

    if match:
        bloco = match.group(1)
    else:
        inicio, fim = texto.find('{'), texto.rfind('}')
        if inicio != -1 and fim != -1:
            bloco = texto[inicio:fim + 1]
        else:
            raise ErroEntrada(f"Não encontrei um bloco {B4}json (plano) na resposta da IA.")
    try:
        return json.loads(bloco)
    except json.JSONDecodeError as e:
        raise ErroEntrada(f"Erro ao decodificar o JSON do plano: {e} | Trecho: {bloco[:200]}...")


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

        # Remove eventuais crases de fechamento de markdown (```) do fim do bloco.
        codigo_limpo = re.sub(r'^`{3,}.*$', '', codigo_bruto, flags=re.MULTILINE)

        # Remove APENAS linhas em branco no começo/fim, preservando a indentação da
        # primeira linha de conteúdo. Um .strip() aqui apagaria os espaços iniciais
        # só da 1ª linha, desalinhando o bloco e fazendo o textwrap.dedent/_reindentar
        # gerar indentação dupla quando a IA manda um trecho já indentado.
        linhas_bloco = codigo_limpo.split("\n")
        while linhas_bloco and not linhas_bloco[0].strip():
            linhas_bloco.pop(0)
        while linhas_bloco and not linhas_bloco[-1].strip():
            linhas_bloco.pop()
        blocos[codigo_id] = "\n".join(linhas_bloco)

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

    Casamento em duas etapas: primeiro o exato (linha a linha, via _normalizar_bloco);
    se ele não achar nada, um fallback tolerante a quebras de linha (rec 2) colapsa
    todo o whitespace — inclusive quebras de linha — dos dois lados, permitindo que
    uma âncora reflada (mesmos tokens, quebras diferentes) case um construto
    equivalente quebrado em várias linhas no disco (ex.: import parentético). O
    fallback exige casamento único e prefere a menor janela por início, para não ser
    guloso. Quando nada casa, o erro traz as linhas do escopo mais próximas da âncora
    (rec 4), revelando como o disco difere do texto ancorado.

    Indentação (WYSIWYG): o código novo entra com a indentação que a IA escreveu,
    corrigida apenas pelo `delta` entre a coluna que ela deu à âncora e a coluna real
    da âncora no arquivo. Assim a indentação RELATIVA escrita pela IA é preservada —
    inclusive quando o trecho insere código num escopo mais raso (ex.: funções de
    módulo logo depois de uma âncora que vive dentro de outra função).
    """
    linhas = fonte.splitlines()

    if no is None:
        win_ini, win_fim = 0, len(linhas)  # janela = arquivo inteiro (0-based, exclusivo)
    else:
        ini, fim = _span_do_no(no)          # 1-based inclusivo
        win_ini, win_fim = ini - 1, fim

    # Coluna que a IA deu à âncora (1ª linha de conteúdo), ANTES de qualquer dedent.
    col_ancora_autorada = 0
    for ln in ancora.split("\n"):
        if ln.strip():
            col_ancora_autorada = len(ln) - len(ln.lstrip())
            break

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

    # Etapa 1: casamento exato, linha a linha (n linhas fixas).
    matches = []
    for i in range(win_ini, win_fim - n + 1):
        if _normalizar_bloco(linhas[i:i + n]) == anc_norm:
            matches.append(i)

    if len(matches) > 1:
        return fonte, (f"âncora ambígua: {len(matches)} ocorrências no escopo do alvo; "
                       "torne a âncora mais específica.")

    if len(matches) == 1:
        m, consumo = matches[0], n
    else:
        # Etapa 2 (rec 2): fallback tolerante a quebras de linha. Colapsa o whitespace
        # dos dois lados e busca, por início, a MENOR janela que case a âncora.
        alvo = _colapsar_ws("\n".join(anc))
        por_inicio = {}
        for i in range(win_ini, win_fim):
            acc = ""
            for j in range(1, (win_fim - i) + 1):
                acc = _colapsar_ws("\n".join(linhas[i:i + j]))
                if len(acc) > len(alvo):
                    break            # só cresce; passou do tamanho, não casa mais
                if acc == alvo:
                    por_inicio[i] = j   # menor j para este início
                    break
        inicios = sorted(por_inicio)
        if len(inicios) == 0:
            return fonte, ("âncora não encontrada dentro do escopo do alvo."
                           + _linhas_proximas(linhas, win_ini, win_fim, ancora))
        if len(inicios) > 1:
            return fonte, (f"âncora ambígua: {len(inicios)} ocorrências (casamento tolerante) "
                           "no escopo do alvo; torne a âncora mais específica.")
        m = inicios[0]
        consumo = por_inicio[m]

    primeira = linhas[m]
    col_real = len(primeira) - len(primeira.lstrip())

    # Corrige só o desencontro âncora-autorada × âncora-real; o resto da indentação
    # relativa que a IA escreveu no `codigo` é mantido intacto.
    delta = col_real - col_ancora_autorada

    if codigo and codigo.strip():
        novo_codigo = _deslocar_bloco(codigo, delta).split("\n")
    else:
        novo_codigo = []  # apagar (substituir por nada)

    if posicao == "substituir":
        novas = linhas[:m] + novo_codigo + linhas[m + consumo:]
    elif posicao == "antes":
        novas = linhas[:m] + novo_codigo + linhas[m:]
    elif posicao == "depois":
        novas = linhas[:m + consumo] + novo_codigo + linhas[m + consumo:]
    else:
        return fonte, f"posição inválida: '{posicao}' (use 'substituir', 'antes' ou 'depois')."

    return "\n".join(novas), None


def _substituir_no_texto(fonte: str, no, codigo_novo: str) -> str:
    """Substitui o bloco correspondente a um nó AST pelo novo código reformatado, preservando o restante do texto."""
    inicio, fim = _span_do_no(no)
    linhas = fonte.splitlines()
    novo = _reindentar(codigo_novo, no.col_offset)
    novas = linhas[:inicio - 1] + novo.split("\n") + linhas[fim:]
    return "\n".join(novas)


def _adicionar_no_texto(fonte: str, codigo_novo: str) -> str:
    """Acrescenta um novo bloco de código ou definição no final do escopo global do arquivo fornecido."""
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


def _contar_mudancas(diff_text: str) -> tuple:
    """Conta linhas adicionadas/removidas num diff unificado (ignora +++/---)."""
    add = dels = 0
    for ln in diff_text.splitlines():
        if ln.startswith("+") and not ln.startswith("+++"):
            add += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            dels += 1
    return add, dels


_RE_HUNK = re.compile(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$')


def _parsear_diff(diff_text: str) -> list:
    """Transforma um diff unificado em linhas estruturadas para render HTML.

    Cada item é uma tupla (tipo, linha_antiga, linha_nova, texto), com tipo em
    {'hunk', 'add', 'del', 'ctx', 'meta'}. Os números de linha saem do cabeçalho
    de cada hunk (@@ -a,b +c,d @@), então não dependem de contar nada à mão.
    """
    linhas = []
    old_ln = new_ln = 0
    for ln in diff_text.splitlines():
        if ln.startswith("diff --git") or ln.startswith("--- ") or ln.startswith("+++ "):
            continue
        m = _RE_HUNK.match(ln)
        if m:
            old_ln, new_ln = int(m.group(1)), int(m.group(2))
            linhas.append(("hunk", None, None, ln))
        elif ln.startswith("+"):
            linhas.append(("add", None, new_ln, ln[1:]))
            new_ln += 1
        elif ln.startswith("-"):
            linhas.append(("del", old_ln, None, ln[1:]))
            old_ln += 1
        elif ln.startswith("\\"):  # "\ No newline at end of file"
            linhas.append(("meta", None, None, ln))
        else:  # contexto (começa com espaço)
            texto = ln[1:] if ln.startswith(" ") else ln
            linhas.append(("ctx", old_ln, new_ln, texto))
            old_ln += 1
            new_ln += 1
    return linhas


_HTML_CSS = """
:root{
  --bg:#f6f8fa;--card:#fff;--border:#d0d7de;--text:#1f2328;--muted:#656d76;
  --add-bg:#e6ffec;--add-ln:#ccffd8;--del-bg:#ffebe9;--del-ln:#ffd7d5;
  --hunk-bg:#ddf4ff;--gutter:#fff;--sign-add:#1a7f37;--sign-del:#cf222e;--accent:#0969da;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0d1117;--card:#0d1117;--border:#30363d;--text:#e6edf3;--muted:#8b949e;
    --add-bg:#12261e;--add-ln:#1b4721;--del-bg:#25171c;--del-ln:#542426;
    --hunk-bg:#121d2f;--gutter:#0d1117;--sign-add:#3fb950;--sign-del:#f85149;--accent:#58a6ff;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.modo{font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px}
.modo.dryrun{background:var(--hunk-bg);color:var(--accent)}
.modo.aplicado{background:var(--add-bg);color:var(--sign-add)}
.resumo{color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.badge{font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace;padding:1px 7px;border-radius:6px}
.badge.add{background:var(--add-bg);color:var(--sign-add)}
.badge.del{background:var(--del-bg);color:var(--sign-del)}
.muted{color:var(--muted);font-weight:400}
.arquivo{border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:16px 0;background:var(--card)}
.arq-head{display:flex;justify-content:space-between;align-items:center;gap:8px;
  padding:8px 14px;background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:1}
.arq-nome{font:600 13px ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
.badges{display:flex;gap:6px;flex:none}
table.diff{width:100%;border-collapse:collapse;
  font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
table.diff td{padding:0 8px;vertical-align:top;white-space:pre-wrap;word-break:break-word}
td.ln{width:1%;min-width:42px;text-align:right;color:var(--muted);
  user-select:none;background:var(--gutter);border-right:1px solid var(--border)}
td.sign{width:1%;text-align:center;user-select:none;padding:0 4px}
td.code{width:100%}
tr.add td.code,tr.add td.sign{background:var(--add-bg)}
tr.add td.ln{background:var(--add-ln)}
tr.add td.sign{color:var(--sign-add)}
tr.del td.code,tr.del td.sign{background:var(--del-bg)}
tr.del td.ln{background:var(--del-ln)}
tr.del td.sign{color:var(--sign-del)}
tr.hunk td{background:var(--hunk-bg);color:var(--muted);padding:4px 8px}
tr.meta td{color:var(--muted);font-style:italic}
.avisos{border:1px solid var(--del-bg);background:var(--del-bg);border-radius:8px;padding:4px 16px;margin:16px 0}
.avisos h2{font-size:14px;color:var(--sign-del)}
.vazio{color:var(--muted)}
"""


def _gerar_html_diff(diffs_arquivos: list, projeto_path: Path, aplicado: bool, erros: list) -> str:
    """Monta uma página HTML (zero-dependência) com os diffs coloridos."""
    total_add = total_del = 0
    blocos = []

    for rel, diff in diffs_arquivos:
        add, dels = _contar_mudancas(diff)
        total_add += add
        total_del += dels

        linhas_html = []
        for tipo, o, n, texto in _parsear_diff(diff):
            if tipo in ("hunk", "meta"):
                linhas_html.append(
                    f'<tr class="{tipo}"><td class="ln"></td><td class="ln"></td>'
                    f'<td class="sign"></td><td class="code">{html.escape(texto)}</td></tr>'
                )
                continue
            sign = {"add": "+", "del": "\u2212", "ctx": ""}[tipo]
            o_s = "" if o is None else str(o)
            n_s = "" if n is None else str(n)
            texto_esc = html.escape(texto) if texto else "&nbsp;"
            linhas_html.append(
                f'<tr class="{tipo}"><td class="ln">{o_s}</td><td class="ln">{n_s}</td>'
                f'<td class="sign">{sign}</td><td class="code">{texto_esc}</td></tr>'
            )

        blocos.append(
            '<section class="arquivo">'
            f'<header class="arq-head"><span class="arq-nome">{html.escape(rel)}</span>'
            f'<span class="badges"><span class="badge add">+{add}</span>'
            f'<span class="badge del">\u2212{dels}</span></span></header>'
            f'<table class="diff">{"".join(linhas_html)}</table>'
            '</section>'
        )

    modo = "Alterações aplicadas" if aplicado else "Pré-visualização (dry-run — nada gravado)"
    modo_cls = "aplicado" if aplicado else "dryrun"

    erros_html = ""
    if erros:
        itens = "".join(f"<li>{html.escape(e)}</li>" for e in erros)
        erros_html = f'<section class="avisos"><h2>Avisos / erros</h2><ul>{itens}</ul></section>'

    corpo = "".join(blocos) if blocos else '<p class="vazio">Nenhuma mudança gerada.</p>'

    return (
        "<!DOCTYPE html>\n"
        '<html lang="pt-br"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>aplicador · diff</title>"
        f"<style>{_HTML_CSS}</style></head><body><div class=\"wrap\">"
        f'<h1>aplicador <span class="modo {modo_cls}">{modo}</span></h1>'
        f'<p class="resumo"><span class="badge add">+{total_add}</span>'
        f'<span class="badge del">\u2212{total_del}</span>'
        f'<span class="muted">· {len(diffs_arquivos)} arquivo(s) · {html.escape(str(projeto_path))}</span></p>'
        f"{erros_html}{corpo}"
        "</div></body></html>"
    )


def aplicar_em_arquivo(rel: str, alvo: Path, ops: list, blocos: dict) -> tuple:
    """Aplica (em memória) todas as operações de um arquivo.

    Lê o texto atual do disco (ou "" se o arquivo não existe) e delega o trabalho de
    aplicação a _aplicar_ops_em_texto (núcleo puro). Wrapper fino: assinatura e retorno
    (texto_original, texto_novo, lista_de_erros) inalterados — o caminho legado do
    executar não percebe diferença.
    """
    original = alvo.read_text(encoding="utf-8", errors="replace") if alvo.exists() else ""
    return _aplicar_ops_em_texto(rel, original, alvo, ops, blocos)


def executar(resposta_path_str: str, projeto_path_str: str,
             aplicar: bool, diff_path_str: str, sem_backup: bool, colar: bool = False):
    """Carrega e aplica (ou simula) o plano de operações.

    Retorna ResultadoAplicar: faz as mutações de arquivo (gravar/.bak/patch), mas
    NÃO imprime, não abre navegador e não encerra o processo. Render de console,
    HTML e browser são responsabilidade da CLI.

    Dois modos:
    - LEGADO (sem acao 'comando'): agrupa por arquivo, calcula diffs, grava se
      `aplicar`. Atômico, com dry-run. Comportamento de sempre.
    - SEQUENCIADO (há acao 'comando'): monta a sequência ordenada (edições + comandos)
      via _montar_passos e NÃO grava aqui — a UI percorre os passos, grava as edições e
      roda os comandos com os gates. O core só prepara (fiel a 'core não toca o mundo');
      marca `sequenciado=True` e expõe `estados_finais` para a UI gravar. `aplicar` não
      grava neste modo.
    """
    projeto_path = Path(projeto_path_str).resolve()
    avisos = []

    try:
        if colar:
            if clipboard is None:
                raise ErroEntrada("clipboard indisponível; não dá para usar --colar.")
            try:
                texto = clipboard.colar()
            except clipboard.ClipboardIndisponivel as e:
                raise ErroEntrada(f"Não consegui ler a área de transferência: {e}")
        else:
            resposta_path = Path(resposta_path_str).resolve()
            if not resposta_path.exists():
                raise ErroEntrada(f"Arquivo com a resposta da IA não encontrado: {resposta_path}")
            texto = resposta_path.read_text(encoding="utf-8", errors="replace")
        plano = carregar_plano(texto)
    except ErroEntrada as e:
        return ResultadoAplicar(sucesso=False, aplicado=aplicar, arquivos=[],
                                total_adicionadas=0, total_removidas=0,
                                caminho_patch=None, caminho_html=None, erros=[str(e)])

    blocos = indexar_blocos_codigo(texto)
    operacoes = plano.get("operacoes", [])

    if not operacoes:
        return ResultadoAplicar(sucesso=True, aplicado=aplicar, arquivos=[],
                                total_adicionadas=0, total_removidas=0,
                                caminho_patch=None, caminho_html=None,
                                avisos=["Nenhuma operação encontrada no plano (chave 'operacoes' vazia)."])

    sequenciado = any(op.get("acao") == "comando" for op in operacoes)

    # ----- MODO SEQUENCIADO (modo C): core prepara, UI executa. Não grava aqui. -----
    if sequenciado:
        passos, arquivos_result, estados_finais, erros_fatais = _montar_passos(operacoes, blocos, projeto_path)
        if erros_fatais:
            return ResultadoAplicar(sucesso=False, aplicado=False, arquivos=[],
                                    total_adicionadas=0, total_removidas=0,
                                    caminho_patch=None, caminho_html=None,
                                    erros=erros_fatais, sequenciado=True)
        total_add = sum(a.adicionadas for a in arquivos_result)
        total_del = sum(a.removidas for a in arquivos_result)
        return ResultadoAplicar(sucesso=True, aplicado=False, arquivos=arquivos_result,
                                total_adicionadas=total_add, total_removidas=total_del,
                                caminho_patch=None, caminho_html=None,
                                avisos=["Plano com comando(s): preparado para execução sequenciada "
                                        "pela interface (o core não executa comandos nem grava)."],
                                passos=passos, sequenciado=True, estados_finais=estados_finais)

    # ----- MODO LEGADO: agrupa por arquivo, grava se `aplicar` (comportamento de sempre). -----
    por_arquivo = defaultdict(list)
    for op in operacoes:
        rel = op.get("arquivo")
        if not rel:
            avisos.append("Operação sem 'arquivo' — ignorada.")
            continue
        por_arquivo[rel].append(op)

    arquivos_result = []
    todos_diffs = []
    total_add = total_del = 0

    for rel, ops in por_arquivo.items():
        alvo = projeto_path / rel
        original, novo, erros = aplicar_em_arquivo(rel, alvo, ops, blocos)
        diff = _gerar_diff(rel, original, novo)
        add = dels = 0
        gravado = False
        backup_criado = False

        if diff:
            add, dels = _contar_mudancas(diff)
            todos_diffs.append(diff)
            if aplicar:
                if alvo.exists() and not sem_backup:
                    shutil.copy2(alvo, alvo.with_suffix(alvo.suffix + ".bak"))
                    backup_criado = True
                alvo.parent.mkdir(parents=True, exist_ok=True)
                conteudo = novo if novo.endswith("\n") else novo + "\n"
                alvo.write_text(conteudo, encoding="utf-8")
                gravado = True

        total_add += add
        total_del += dels
        arquivos_result.append(ResultadoArquivoAplicado(
            caminho=rel, adicionadas=add, removidas=dels, diff=diff,
            gravado=gravado, backup_criado=backup_criado, erros=erros))

    caminho_patch = None
    if diff_path_str and todos_diffs:
        try:
            Path(diff_path_str).write_text("\n".join(todos_diffs) + "\n", encoding="utf-8")
            caminho_patch = str(Path(diff_path_str).resolve())
        except Exception as e:
            avisos.append(f"Não consegui salvar o patch combinado: {e}")

    return ResultadoAplicar(sucesso=True, aplicado=aplicar, arquivos=arquivos_result,
                            total_adicionadas=total_add, total_removidas=total_del,
                            caminho_patch=caminho_patch, caminho_html=None,
                            avisos=avisos)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aplica alterações da IA substituindo nós (funções/classes) por nome via AST."
    )
    parser.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta da IA (plano + blocos de código).")
    parser.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto (ex: ../VisualizadorPN).")
    parser.add_argument("--aplicar", action="store_true", help="Grava as alterações nos arquivos (default: dry-run).")
    parser.add_argument("--diff", dest="diff_path", default=None, help="Salva o patch unificado combinado neste caminho.")
    parser.add_argument("--sem-backup", action="store_true", help="Não cria arquivos .bak ao gravar.")
    parser.add_argument(
        "--colar",
        action="store_true",
        help="Lê a resposta da IA da área de transferência em vez de um arquivo "
             "(assim você não passa 'resposta_ia').",
    )
    parser.add_argument(
        "--html-diff",
        nargs="?",
        const="",
        default=None,
        metavar="ARQUIVO.html",
        help="Gera uma página HTML com os diffs coloridos e abre no navegador. "
             "Informe um caminho para salvar o HTML; sem valor, usa um arquivo temporário.",
    )
    parser.add_argument("--instrucoes", action="store_true", help="Imprime as instruções para colar no chat com a IA e sai.")

    args = parser.parse_args()

    if args.instrucoes:
        print(INSTRUCOES_IA)
        sys.exit(0)

    # Reorganiza os posicionais conforme --colar (com --colar não se passa resposta_ia).
    posicionais = [p for p in (args.resposta_ia, args.diretorio_projeto) if p is not None]
    if args.colar:
        if len(posicionais) != 1:
            parser.error("com --colar, informe apenas: diretorio_projeto.")
        args.resposta_ia = None
        args.diretorio_projeto = posicionais[0]
    else:
        if len(posicionais) != 2:
            parser.error("informe 'resposta_ia' e 'diretorio_projeto' "
                         "(ou use --colar passando só o diretório, ou --instrucoes).")
        args.resposta_ia, args.diretorio_projeto = posicionais

    executar(args.resposta_ia, args.diretorio_projeto, args.aplicar, args.diff_path,
             args.sem_backup, args.html_diff, args.colar)

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


def _deslocar_bloco(codigo: str, delta: int) -> str:
    """Desloca o bloco inteiro por `delta` colunas, preservando a indentação
    RELATIVA que a IA escreveu (a forma do código não muda; só a coluna-base).

    delta > 0 adiciona espaços à esquerda de cada linha não-vazia; delta < 0 remove
    espaços à esquerda, no máximo até a indentação mínima do bloco (assim nunca "come"
    conteúdo nem distorce a estrutura). Linhas em branco continuam vazias.
    """
    if delta == 0:
        return codigo
    linhas = codigo.split("\n")
    if delta > 0:
        prefixo = " " * delta
        return "\n".join(prefixo + ln if ln.strip() else "" for ln in linhas)
    indents = [len(ln) - len(ln.lstrip()) for ln in linhas if ln.strip()]
    if not indents:
        return codigo
    shift = min(-delta, min(indents))
    return "\n".join(ln[shift:] if ln.strip() else "" for ln in linhas)


def _colapsar_ws(texto: str) -> str:
    """Colapsa todo run de whitespace (inclusive quebras de linha) em um único
    espaço e remove as pontas.

    Usado SÓ no casamento tolerante de âncora (rec 2): permite casar uma âncora
    reflada — mesmos tokens, quebras de linha diferentes — contra o texto do disco.
    Não influencia o posicionamento do código novo, que continua respeitando a
    estrutura real das linhas.
    """
    return " ".join(texto.split())


def _linhas_proximas(linhas: list, win_ini: int, win_fim: int, ancora: str, n: int = 3) -> str:
    """Diagnóstico de âncora que não casou (rec 4).

    Devolve as `n` linhas do escopo mais parecidas com a âncora (por similaridade),
    cada uma com seu número de linha 1-based no arquivo, para revelar como o disco
    difere do texto que a IA ancorou — o caso típico é um import que no disco está
    parentético/multilinha e na âncora veio em linha única. Retorna '' se o escopo
    não tiver linhas com conteúdo.
    """
    import difflib  # uso pontual, só neste caminho de erro
    alvo = _colapsar_ws(ancora)
    pontuadas = []
    for i in range(win_ini, win_fim):
        if not linhas[i].strip():
            continue
        escore = difflib.SequenceMatcher(None, alvo, _colapsar_ws(linhas[i])).ratio()
        pontuadas.append((escore, i))
    if not pontuadas:
        return ""
    pontuadas.sort(key=lambda t: t[0], reverse=True)
    melhores = sorted(idx for _, idx in pontuadas[:n])  # reordena por posição no arquivo
    corpo = "\n".join(f"    L{i + 1}: {linhas[i]}" for i in melhores)
    return "\n  linhas mais próximas no escopo:\n" + corpo


def _formatar_import_from(modulo: str, nomes: list) -> str:
    """Formata um `from <modulo> import (...)` na forma canônica multilinha:
    um nome por linha, com vírgula final e entre parênteses.

    Forma ÚNICA e previsível, independente da quantidade de nomes — assim a IA
    sempre vê o mesmo formato ao reler o arquivo (via `arquivos_completos`), sem a
    ambiguidade linha-única × parentético que originou o bug de âncora em imports.
    """
    corpo = "".join(f"    {n},\n" for n in nomes)
    return f"from {modulo} import (\n{corpo})"


def _adicionar_import_no_texto(fonte: str, modulo: str, nomes: list):
    """Insere `nomes` num `from <modulo> import ...` de nível de módulo, via AST.

    Imune ao formato do import no disco (linha única ou multilinha entre
    parênteses): localiza o nó ImportFrom pelo AST e reescreve o statement inteiro
    na forma canônica (_formatar_import_from). Como não depende de casar texto,
    resolve na origem a classe de bug em que a âncora de um import não casava por
    diferença de formatação.

    Comportamento:
      - módulo já importado: acrescenta apenas os nomes ausentes (dedup; se todos
        já existem, é no-op e devolve a fonte intacta);
      - módulo ausente: cria o import novo após o último import de nível de módulo;
        se não houver imports, após o docstring do módulo; sem docstring, no topo.

    Escopo enxuto: só mexe em `from X import` absoluto (level 0). Não trata
    `import X`, imports relativos nem aliases (`as`) — para esses, use `trecho`.
    Retorna (nova_fonte, erro_ou_None).
    """
    for nome in nomes:
        if not isinstance(nome, str) or not nome.isidentifier():
            return fonte, (f"nome de import inválido: {nome!r}. Use identificadores "
                           "simples (sem 'as', sem '.'); aliases e imports relativos "
                           "ficam fora desta ação — use 'trecho'.")
    try:
        arvore = ast.parse(fonte)
    except SyntaxError as e:
        return fonte, f"não consegui parsear o arquivo para inserir o import: {e}"

    linhas = fonte.splitlines()

    alvo_no = None
    ultimo_import_fim = None
    for no in arvore.body:
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            ultimo_import_fim = no.end_lineno
        if (alvo_no is None and isinstance(no, ast.ImportFrom)
                and no.level == 0 and (no.module or "") == modulo):
            alvo_no = no  # primeiro `from <modulo> import` vence

    if alvo_no is not None:
        existentes = [a.name for a in alvo_no.names]
        faltantes = [n for n in nomes if n not in existentes]
        if not faltantes:
            return fonte, None  # todos os nomes já presentes
        bloco = _formatar_import_from(modulo, existentes + faltantes)
        ini, fim = _span_do_no(alvo_no)  # 1-based inclusivo
        novas = linhas[:ini - 1] + bloco.split("\n") + linhas[fim:]
        return "\n".join(novas), None

    bloco = _formatar_import_from(modulo, list(nomes))
    if ultimo_import_fim is not None:
        novas = linhas[:ultimo_import_fim] + bloco.split("\n") + linhas[ultimo_import_fim:]
        return "\n".join(novas), None

    corpo_mod = arvore.body
    if (corpo_mod and isinstance(corpo_mod[0], ast.Expr)
            and isinstance(getattr(corpo_mod[0], "value", None), ast.Constant)
            and isinstance(corpo_mod[0].value.value, str)):
        pos = corpo_mod[0].end_lineno
        novas = linhas[:pos] + [""] + bloco.split("\n") + linhas[pos:]
        return "\n".join(novas), None

    novas = bloco.split("\n") + [""] + linhas
    return "\n".join(novas), None


def _aplicar_ops_em_texto(rel: str, original: str, alvo: Path, ops: list, blocos: dict) -> tuple:
    """Aplica `ops` a um TEXTO de partida (`original`), sem ler o disco.

    Núcleo puro extraído de aplicar_em_arquivo: recebe o texto inicial como argumento
    em vez de lê-lo do disco, para que o interpretador de sequência (modo C) possa
    encadear várias edições ao mesmo arquivo em memória (a 2ª parte do que a 1ª
    produziu). `alvo` é usado só para metadados do caminho (`alvo.suffix`), nunca para
    reler conteúdo. Retorna (original, novo, erros) — mesma tupla de aplicar_em_arquivo.
    """
    erros = []
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
                    erros.append(f"[{rel}] não consegui parsear o estado atual do arquivo: {e} "
                                 "(ações por nó exigem Python válido — corrija a sintaxe e rode de novo, "
                                 "ou use \"acao\": \"arquivo\").")
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
        if acao == "adicionar_import":
            if alvo.suffix != ".py":
                erros.append(f"[{rel}] 'adicionar_import' exige arquivo .py.")
                continue
            modulo = op.get("modulo")
            nomes = op.get("nomes") or []
            if not modulo or not isinstance(nomes, list) or not nomes:
                erros.append(f"[{rel}] 'adicionar_import' exige 'modulo' (str) e "
                             "'nomes' (lista não-vazia).")
                continue
            resultado, erro = _adicionar_import_no_texto(novo, modulo, nomes)
            if erro:
                erros.append(f"[{rel}] adicionar_import '{modulo}': {erro}")
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


def _validar_comando(op: dict):
    """Valida a forma de uma acao 'comando' (critério ii). Erro-como-dado, não executa.

    Devolve (PassoComando, erro_ou_None). Checa tipos: comando string não-vazia;
    shell suportado; espera_exit int ou ausente; espera_conter string ou ausente;
    timeout int positivo ou ausente. Monta só o PEDIDO — a execução é da UI (5c).
    """
    comando = op.get("comando")
    if not isinstance(comando, str) or not comando.strip():
        return None, "acao 'comando' exige 'comando' (string não-vazia)."

    shell = op.get("shell", "powershell")
    if shell not in ("powershell", "pwsh"):
        return None, f"shell '{shell}' não suportado (use 'powershell' ou 'pwsh')."

    espera_exit = op.get("espera_exit")
    if espera_exit is not None and not isinstance(espera_exit, int):
        return None, "'espera_exit' deve ser inteiro ou ausente."

    espera_conter = op.get("espera_conter")
    if espera_conter is not None and not isinstance(espera_conter, str):
        return None, "'espera_conter' deve ser string ou ausente."

    timeout = op.get("timeout")
    if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0):
        return None, "'timeout' deve ser inteiro positivo ou ausente."

    return PassoComando(
        comando=comando, shell=shell, descricao=op.get("descricao", ""),
        espera_exit=espera_exit, espera_conter=espera_conter, timeout=timeout), None


def _montar_passos(operacoes: list, blocos: dict, projeto_path: Path):
    """Interpretador de sequência (modo C): percorre as operações na ORDEM do plano.

    Encadeia edições ao mesmo arquivo em memória via _aplicar_ops_em_texto (núcleo
    puro): a 2ª edição de um arquivo parte do que a 1ª produziu. Comandos NÃO são
    executados aqui (efeito de mundo é da UI) e não alteram o estado — o core prepara
    a sequência otimista completa; a UI a executa até onde os gates permitirem.

    Devolve (passos, arquivos_result, estados_finais, erros_fatais):
    - passos: lista ordenada de PassoPlano (edição ou comando), preservando a ordem
      original do plano — é isto que honra o intercalamento com gates;
    - arquivos_result: agregado por arquivo (uma entrada, diff disco->estado final),
      para compatibilidade com quem lê `.arquivos` (histórico, GUI);
    - estados_finais: dict rel -> texto final acumulado, que a UI grava no disco ao
      percorrer os passos de edição (a 5c consome isto no executar_sequencia);
    - erros_fatais: comando malformado ou op de edição sem 'arquivo'. Se não-vazio, a
      preparação é abortada (o executar não grava nada).
    """
    passos = []
    estados = {}            # rel -> texto acumulado em memória
    originais = {}          # rel -> texto original em disco (base do diff agregado)
    erros_por_arquivo = {}  # rel -> [erros de edição] (dict próprio, não misturado a estados)
    ordem_arquivos = []     # 1ª aparição de cada arquivo editado (ordem estável do agregado)
    erros_fatais = []

    for i, op in enumerate(operacoes):
        acao = op.get("acao")

        if acao == "comando":
            pc, erro = _validar_comando(op)
            if erro:
                erros_fatais.append(f"[passo {i}] {erro}")
                continue
            passos.append(PassoPlano(tipo="comando", ordem=i, comando=pc,
                                     resultado_comando=ResultadoComando()))
            continue

        # Edição: exige 'arquivo'.
        rel = op.get("arquivo")
        if not rel:
            erros_fatais.append(f"[passo {i}] operação de edição sem 'arquivo'.")
            continue

        alvo = projeto_path / rel
        if rel not in estados:
            texto = alvo.read_text(encoding="utf-8", errors="replace") if alvo.exists() else ""
            estados[rel] = texto
            originais[rel] = texto
            erros_por_arquivo[rel] = []
            ordem_arquivos.append(rel)

        antes = estados[rel]
        _orig, depois, erros_op = _aplicar_ops_em_texto(rel, antes, alvo, [op], blocos)
        estados[rel] = depois
        erros_por_arquivo[rel].extend(erros_op)
        passos.append(PassoPlano(tipo="edicao", ordem=i, caminho=rel))

    if erros_fatais:
        return [], [], {}, erros_fatais

    arquivos_result = []
    for rel in ordem_arquivos:
        diff = _gerar_diff(rel, originais[rel], estados[rel])
        add, dels = _contar_mudancas(diff) if diff else (0, 0)
        arquivos_result.append(ResultadoArquivoAplicado(
            caminho=rel, adicionadas=add, removidas=dels, diff=diff,
            gravado=False, backup_criado=False, erros=erros_por_arquivo[rel]))

    return passos, arquivos_result, dict(estados), []
