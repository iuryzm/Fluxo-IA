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
