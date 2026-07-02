"""Testes de aplicador: contar mudancas, guarda-corpo de sintaxe, plano invalido."""
from pyresumidor.core import aplicador


def test_contar_mudancas():
    diff = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-linha velha\n"
        "+linha nova\n"
        " contexto\n"
    )
    add, dels = aplicador._contar_mudancas(diff)
    # +++ e --- nao contam; so as linhas reais
    assert add == 1
    assert dels == 1


def test_substituir_funcao_simples(projeto):
    alvo = projeto / "exemplo.py"
    ops = [{"acao": "substituir", "arquivo": "exemplo.py", "tipo": "funcao",
            "alvo": "funcao_solta", "codigo_id": "b1"}]
    blocos = {"b1": "def funcao_solta(x):\n    return x * 99\n"}
    original, novo, erros = aplicador.aplicar_em_arquivo("exemplo.py", alvo, ops, blocos)
    assert not erros
    assert "x * 99" in novo
    assert "x + 1" not in novo


def test_guarda_corpo_recusa_sintaxe_invalida(projeto):
    # Regressao: um .py nunca pode ser gravado com sintaxe quebrada
    alvo = projeto / "exemplo.py"
    ops = [{"acao": "substituir", "arquivo": "exemplo.py", "tipo": "funcao",
            "alvo": "funcao_solta", "codigo_id": "b1"}]
    blocos = {"b1": "def funcao_solta(x:\n    return"}  # sintaxe invalida
    original, novo, erros = aplicador.aplicar_em_arquivo("exemplo.py", alvo, ops, blocos)
    # nada aplicado: novo == original e erro reportado
    assert novo == original
    assert erros


def test_plano_invalido_vira_erro(projeto, tmp_path):
    resposta = tmp_path / "resp.md"
    resposta.write_text("nao ha json nenhum aqui", encoding="utf-8")
    res = aplicador.executar(str(resposta), str(projeto), aplicar=False,
                             diff_path_str=None, sem_backup=False)
    assert res.sucesso is False
    assert res.erros


def test_aplicar_dry_run_nao_grava(projeto, tmp_path):
    # Monta uma resposta valida (plano + bloco) e confere que dry-run nao toca o arquivo
    cb = chr(96) * 3
    resposta = tmp_path / "resp.md"
    resposta.write_text(
        f"{cb}json\n"
        '{"operacoes": [{"acao": "substituir", "arquivo": "exemplo.py", '
        '"tipo": "funcao", "alvo": "funcao_solta", "codigo_id": "b1"}]}\n'
        f"{cb}\n\n"
        f"{cb}python\n"
        "# --- id=b1 ---\n"
        "def funcao_solta(x):\n    return x * 99\n"
        f"{cb}\n",
        encoding="utf-8",
    )
    antes = (projeto / "exemplo.py").read_text(encoding="utf-8")
    res = aplicador.executar(str(resposta), str(projeto), aplicar=False,
                             diff_path_str=None, sem_backup=False)
    depois = (projeto / "exemplo.py").read_text(encoding="utf-8")
    assert res.sucesso is True
    assert res.aplicado is False
    assert antes == depois            # dry-run nao grava
    assert res.total_adicionadas > 0  # mas calcula o diff


def test_adicionar_import_cria_apos_ultimo_import():
    """Módulo ausente: o import novo entra logo após o último import existente,
    na forma canônica multilinha, e o resultado continua sendo Python válido."""
    fonte = (
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def foo():\n"
        "    pass\n"
    )
    novo, erro = aplicador._adicionar_import_no_texto(fonte, "coletores.base", ["Coletor"])
    assert erro is None
    assert "from coletores.base import (" in novo
    # Posicionado depois dos imports e antes do código.
    assert novo.index("coletores.base") > novo.index("pathlib")
    assert novo.index("coletores.base") < novo.index("def foo")
    compile(novo, "<teste>", "exec")  # não levanta => sintaxe válida


def test_adicionar_import_nome_novo_sem_duplicar():
    """Módulo já importado (parentético): acrescenta só o nome ausente e não
    duplica o que já existe, reescrevendo o statement na forma canônica."""
    fonte = (
        "from componentes.fluxos_model import (\n"
        "    TIPO_ABRIR,\n"
        "    TIPOS_FILTRO,\n"
        ")\n"
        "\n"
        "x = 1\n"
    )
    novo, erro = aplicador._adicionar_import_no_texto(
        fonte, "componentes.fluxos_model", ["TIPOS_FILTRO", "TIPO_OPERACAO"])
    assert erro is None
    assert novo.count("TIPOS_FILTRO") == 1  # não duplicou o já existente
    assert "TIPO_OPERACAO" in novo
    assert "TIPO_ABRIR" in novo
    compile(novo, "<teste>", "exec")


def test_adicionar_import_todos_presentes_e_noop():
    """Se todos os nomes já estão no import, é no-op: devolve a fonte intacta e
    sem erro (não reescreve nem reordena nada)."""
    fonte = (
        "from x import (\n"
        "    A,\n"
        "    B,\n"
        ")\n"
    )
    novo, erro = aplicador._adicionar_import_no_texto(fonte, "x", ["A", "B"])
    assert erro is None
    assert novo == fonte


def test_adicionar_import_nome_invalido_vira_erro():
    """Nome com ponto ou 'as' não é identificador simples: a ação recusa com erro
    claro e não altera a fonte (aliases/relativos ficam para o 'trecho')."""
    fonte = "import os\n"
    novo, erro = aplicador._adicionar_import_no_texto(fonte, "x.y", ["Foo.bar"])
    assert erro is not None
    assert "inválido" in erro
    assert novo == fonte  # nada alterado
    # 'as' embutido no nome também é recusado.
    novo2, erro2 = aplicador._adicionar_import_no_texto(fonte, "x.y", ["Foo as F"])
    assert erro2 is not None
    assert novo2 == fonte


def test_adicionar_import_sem_imports_vai_ao_topo():
    """Sem imports e sem docstring de módulo: o import entra no topo do arquivo."""
    fonte = "x = 1\n"
    novo, erro = aplicador._adicionar_import_no_texto(fonte, "mod", ["A"])
    assert erro is None
    assert novo.startswith("from mod import (")
    compile(novo, "<teste>", "exec")


def test_adicionar_import_respeita_docstring_de_modulo():
    """Sem imports, mas com docstring de módulo: o import entra logo após a
    docstring (nunca antes dela)."""
    fonte = '"""Modulo de teste."""\n\nx = 1\n'
    novo, erro = aplicador._adicionar_import_no_texto(fonte, "mod", ["A"])
    assert erro is None
    assert novo.index("from mod import") > novo.index('"""Modulo de teste."""')
    assert novo.index("from mod import") < novo.index("x = 1")
    compile(novo, "<teste>", "exec")
