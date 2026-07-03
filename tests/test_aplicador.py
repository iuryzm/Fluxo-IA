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


def test_allowlist_le_negacoes(tmp_path):
    """_padroes_allowlist devolve os padrões CRUS das negações, ignorando as de
    diretório (terminadas em '/') e as linhas de ignore."""
    (tmp_path / ".gitignore").write_text("*\n!*/\n!a.py\n!src/*.py\n", encoding="utf-8")
    from pyresumidor.core.aplicador import _padroes_allowlist
    assert _padroes_allowlist(tmp_path) == ["a.py", "src/*.py"]


def test_allowlist_ausente_devolve_none(tmp_path):
    """Sem .gitignore (ou sem negações), a guarda não se aplica: None."""
    from pyresumidor.core.aplicador import _padroes_allowlist
    assert _padroes_allowlist(tmp_path) is None
    (tmp_path / ".gitignore").write_text("*.pyc\nbuild/\n", encoding="utf-8")
    assert _padroes_allowlist(tmp_path) is None


def test_guarda_existente_fora_do_allowlist_e_erro(tmp_path):
    """Cenário do incidente: alvo existe no disco, invisível no mapa -> erro fatal."""
    (tmp_path / ".gitignore").write_text("*\n!a.py\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("conteudo nunca visto\n", encoding="utf-8")
    from pyresumidor.core.aplicador import _validar_acoes_arquivo
    ops = [{"acao": "arquivo", "arquivo": "b.py", "codigo_id": "b1"}]
    erros, avisos = _validar_acoes_arquivo(ops, tmp_path)
    assert len(erros) == 1 and "b.py" in erros[0] and "allowlist" in erros[0]
    assert avisos == []


def test_guarda_sobrescrever_true_vira_aviso(tmp_path):
    """A válvula 'sobrescrever': true fura o erro e vira aviso. Só True booleano."""
    (tmp_path / ".gitignore").write_text("*\n!a.py\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x\n", encoding="utf-8")
    from pyresumidor.core.aplicador import _validar_acoes_arquivo
    ops = [{"acao": "arquivo", "arquivo": "b.py", "codigo_id": "b1", "sobrescrever": True}]
    erros, avisos = _validar_acoes_arquivo(ops, tmp_path)
    assert erros == []
    assert len(avisos) == 1 and "autorizada" in avisos[0]
    # Valor truthy não-booleano NÃO autoriza.
    ops = [{"acao": "arquivo", "arquivo": "b.py", "codigo_id": "b1", "sobrescrever": "sim"}]
    erros, _avisos = _validar_acoes_arquivo(ops, tmp_path)
    assert len(erros) == 1


def test_guarda_listado_ou_novo_nao_bloqueia(tmp_path):
    """Quadrantes benignos: existente listado (inclusive por glob) e novo listado
    passam limpos; novo NÃO listado passa com aviso."""
    (tmp_path / ".gitignore").write_text("*\n!a.py\n!src/*.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("y\n", encoding="utf-8")
    from pyresumidor.core.aplicador import _validar_acoes_arquivo
    ops = [
        {"acao": "arquivo", "arquivo": "a.py", "codigo_id": "b1"},        # existe, listado
        {"acao": "arquivo", "arquivo": "src/m.py", "codigo_id": "b2"},    # existe, casa glob
        {"acao": "arquivo", "arquivo": "src/novo.py", "codigo_id": "b3"}, # novo, casa glob
        {"acao": "arquivo", "arquivo": "solto.txt", "codigo_id": "b4"},   # novo, fora
    ]
    erros, avisos = _validar_acoes_arquivo(ops, tmp_path)
    assert erros == []
    assert len(avisos) == 1 and "solto.txt" in avisos[0]


def test_guarda_sem_gitignore_so_avisa(tmp_path):
    """Projeto sem allowlist: a guarda não bloqueia nada, só um aviso informativo."""
    (tmp_path / "b.py").write_text("x\n", encoding="utf-8")
    from pyresumidor.core.aplicador import _validar_acoes_arquivo
    ops = [{"acao": "arquivo", "arquivo": "b.py", "codigo_id": "b1"}]
    erros, avisos = _validar_acoes_arquivo(ops, tmp_path)
    assert erros == []
    assert len(avisos) == 1 and "não aplicada" in avisos[0]
