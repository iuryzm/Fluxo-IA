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
    col_real = len(primeira) - len(primeira.lstrip())

    # Corrige só o desencontro âncora-autorada × âncora-real; o resto da indentação
    # relativa que a IA escreveu no `codigo` é mantido intacto.
    delta = col_real - col_ancora_autorada

    if codigo and codigo.strip():
        novo_codigo = _deslocar_bloco(codigo, delta).split("\n")
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
             aplicar: bool, diff_path_str: str, sem_backup: bool, html_diff=None, colar=False):
    """Orquestra o carregamento e aplicação do plano de operações, exibindo os diffs com colorização no console."""
    projeto_path = Path(projeto_path_str).resolve()

    if colar:
        if clipboard is None:
            print("\033[31m❌ clipboard.py não encontrado ao lado deste script; não dá para usar --colar.\033[0m")
            sys.exit(1)
        try:
            texto = clipboard.colar()
        except clipboard.ClipboardIndisponivel as e:
            print(f"\033[31m❌ Não consegui ler a área de transferência: {e}\033[0m")
            sys.exit(1)
        print("📋 Lendo a resposta da IA da área de transferência...")
    else:
        resposta_path = Path(resposta_path_str).resolve()
        if not resposta_path.exists():
            print(f"\033[31m❌ Arquivo com a resposta da IA não encontrado: {resposta_path}\033[0m")
            sys.exit(1)
        texto = resposta_path.read_text(encoding="utf-8", errors="replace")
    plano = carregar_plano(texto)
    blocos = indexar_blocos_codigo(texto)
    operacoes = plano.get("operacoes", [])

    if not operacoes:
        print("\033[33m⚠️ Nenhuma operação encontrada no plano (chave 'operacoes' vazia).\033[0m")
        sys.exit(0)

    print(f"\033[36m🔧 {len(operacoes)} operação(ões) no plano · {len(blocos)} bloco(s) de código encontrados.\033[0m")
    print(f"📂 Projeto: {projeto_path}")
    print(f"\033[1;32m✍️  MODO APLICAR (vai gravar)\033[0m" if aplicar else f"\033[1;33m👀 MODO DRY-RUN (nada será gravado)\033[0m")
    print()

    por_arquivo = defaultdict(list)
    for op in operacoes:
        rel = op.get("arquivo")
        if not rel:
            print("\033[33m⚠️ Operação sem 'arquivo' — ignorada.\033[0m")
            continue
        por_arquivo[rel].append(op)

    todos_diffs = []
    diffs_arquivos = []  # (rel, diff) para o render HTML
    total_erros = []

    for rel, ops in por_arquivo.items():
        alvo = projeto_path / rel
        original, novo, erros = aplicar_em_arquivo(rel, alvo, ops, blocos)
        total_erros.extend(erros)

        diff = _gerar_diff(rel, original, novo)
        if diff:
            todos_diffs.append(diff)
            diffs_arquivos.append((rel, diff))
            print(f"\033[1;34m📝 {rel}\033[0m")

            # Realiza a colorização linha por linha do diff unificado estrutural
            for linha in diff.splitlines():
                if linha.startswith("+") and not linha.startswith("+++"):
                    print(f"\033[32m{linha}\033[0m")
                elif linha.startswith("-") and not linha.startswith("---"):
                    print(f"\033[31m{linha}\033[0m")
                elif linha.startswith("@@"):
                    print(f"\033[36m{linha}\033[0m")
                else:
                    print(linha)

            if aplicar:
                if alvo.exists() and not sem_backup:
                    shutil.copy2(alvo, alvo.with_suffix(alvo.suffix + ".bak"))
                alvo.parent.mkdir(parents=True, exist_ok=True)
                conteudo = novo if novo.endswith("\n") else novo + "\n"
                alvo.write_text(conteudo, encoding="utf-8")
                print(f"   \033[32m✅ gravado{'' if sem_backup else ' (backup .bak criado)'}\033[0m\n")
            else:
                print()
        else:
            print(f"➖ {rel}: nenhuma mudança gerada.\n")

    if diff_path_str and todos_diffs:
        Path(diff_path_str).write_text("\n".join(todos_diffs) + "\n", encoding="utf-8")
        print(f"\033[32m💾 Patch combinado salvo em: {diff_path_str}\033[0m")
        print(f"   Aplicar com Git:   git apply {diff_path_str}")
        print(f"   Conferir antes:    git apply --check {diff_path_str}")

    if total_erros:
        print("\n\033[1;31m⚠️ Avisos/erros:\033[0m")
        for e in total_erros:
            print(f"   \033[31m- {e}\033[0m")

    if html_diff is not None:
        if diffs_arquivos or total_erros:
            pagina = _gerar_html_diff(diffs_arquivos, projeto_path, aplicar, total_erros)
            if html_diff:  # caminho explícito informado pelo usuário
                destino = Path(html_diff).resolve()
                destino.parent.mkdir(parents=True, exist_ok=True)
            else:          # sem valor: usa um arquivo temporário
                tmp = tempfile.NamedTemporaryFile(prefix="aplicador_diff_", suffix=".html", delete=False)
                tmp.close()
                destino = Path(tmp.name)
            destino.write_text(pagina, encoding="utf-8")
            print(f"\n🌐 Diff em HTML salvo em: {destino}")
            try:
                if webbrowser.open(destino.as_uri()):
                    print("   Abrindo no navegador...")
                else:
                    print("   (não consegui abrir um navegador; abra o arquivo acima manualmente.)")
            except Exception:
                print("   (não consegui abrir um navegador; abra o arquivo acima manualmente.)")
        else:
            print("\n🌐 --html-diff: nada para mostrar (nenhuma mudança gerada).")

    if not aplicar and todos_diffs:
        print("\n\033[33mℹ️ Isto foi um dry-run. Use --aplicar para gravar, ou --diff arquivo.patch para salvar o patch.\033[0m")


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
