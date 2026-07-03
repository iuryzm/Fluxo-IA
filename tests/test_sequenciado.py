"""Testes do modo sequenciado (modo C): interpretador _montar_passos + bifurcação.

Cobrem: ordem dos passos preservada, dupla edição ao mesmo arquivo encadeando em
memória, comando não sumindo no filtro de 'arquivo', comando malformado abortando a
preparação, e o caminho LEGADO permanecendo intacto (plano sem comando não é
sequenciado e grava normalmente). Nada aqui EXECUTA comando — o core só prepara.
"""
import json
from pathlib import Path
from pyresumidor.core import aplicador


def _resposta(tmp_path, plano: dict, blocos_texto: str = ""):
    """Grava a resposta (plano json + blocos) e devolve (resposta_path, projeto_path)."""
    projeto = tmp_path / "proj"
    projeto.mkdir(exist_ok=True)
    corpo = "```json\n" + json.dumps(plano) + "\n```\n" + blocos_texto
    resposta = tmp_path / "resposta.md"
    resposta.write_text(corpo, encoding="utf-8")
    return str(resposta), str(projeto)


def test_plano_sem_comando_nao_e_sequenciado(tmp_path):
    """Caminho legado: plano de pura edição não marca sequenciado e grava com --aplicar."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    (projeto / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    plano = {"operacoes": [
        {"acao": "substituir", "arquivo": "m.py", "tipo": "funcao", "alvo": "f", "codigo_id": "b1"}]}
    blocos = "```python\n# --- id=b1 ---\ndef f():\n    return 2\n```\n"
    r, p = _resposta(tmp_path, plano, blocos)
    res = aplicador.executar(r, p, aplicar=True, diff_path_str=None, sem_backup=True)
    assert res.sucesso is True
    assert res.sequenciado is False
    assert res.aplicado is True
    assert (Path(p) / "m.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"


def test_plano_com_comando_e_sequenciado_e_nao_grava(tmp_path):
    """Modo C: plano com comando marca sequenciado, monta passos e NÃO grava."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    (projeto / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    plano = {"operacoes": [
        {"acao": "substituir", "arquivo": "m.py", "tipo": "funcao", "alvo": "f", "codigo_id": "b1"},
        {"acao": "comando", "comando": "pytest -q", "espera_exit": 0}]}
    blocos = "```python\n# --- id=b1 ---\ndef f():\n    return 2\n```\n"
    r, p = _resposta(tmp_path, plano, blocos)
    res = aplicador.executar(r, p, aplicar=True, diff_path_str=None, sem_backup=True)
    assert res.sequenciado is True
    assert res.aplicado is False                       # não gravou
    assert (Path(p) / "m.py").read_text(encoding="utf-8") == "def f():\n    return 1\n"  # disco intacto
    # dois passos, na ordem: edicao (0) depois comando (1)
    assert [pp.tipo for pp in res.passos] == ["edicao", "comando"]
    assert res.passos[1].comando.comando == "pytest -q"
    assert res.passos[1].comando.espera_exit == 0
    assert res.passos[1].resultado_comando.executado is False


def test_ordem_intercalada_preservada(tmp_path):
    """A ordem do plano é a ordem dos passos, mesmo intercalando edição e comando."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    (projeto / "a.py").write_text("x = 1\n", encoding="utf-8")
    plano = {"operacoes": [
        {"acao": "comando", "comando": "echo antes"},
        {"acao": "arquivo", "arquivo": "a.py", "codigo_id": "b1"},
        {"acao": "comando", "comando": "echo depois"}]}
    blocos = "```python\n# --- id=b1 ---\nx = 2\n```\n"
    r, p = _resposta(tmp_path, plano, blocos)
    res = aplicador.executar(r, p, aplicar=False, diff_path_str=None, sem_backup=True)
    assert [pp.tipo for pp in res.passos] == ["comando", "edicao", "comando"]
    assert [pp.ordem for pp in res.passos] == [0, 1, 2]


def test_dupla_edicao_mesmo_arquivo_encadeia(tmp_path):
    """Duas edições ao mesmo arquivo acumulam: a 2ª parte do resultado da 1ª."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    (projeto / "a.py").write_text("original\n", encoding="utf-8")
    plano = {"operacoes": [
        {"acao": "arquivo", "arquivo": "a.py", "codigo_id": "b1"},
        {"acao": "comando", "comando": "echo meio"},
        {"acao": "arquivo", "arquivo": "a.py", "codigo_id": "b2"}]}
    blocos = ("```python\n# --- id=b1 ---\nprimeira\n"
              "# --- id=b2 ---\nsegunda\n```\n")
    r, p = _resposta(tmp_path, plano, blocos)
    res = aplicador.executar(r, p, aplicar=False, diff_path_str=None, sem_backup=True)
    # Agregado: uma entrada para a.py, diff disco->final (segunda), não duas entradas.
    a_py = [a for a in res.arquivos if a.caminho == "a.py"]
    assert len(a_py) == 1
    assert "segunda" in a_py[0].diff        # estado final é o da 2ª edição
    # passos: edicao, comando, edicao (a 2ª existe como passo próprio)
    assert [pp.tipo for pp in res.passos] == ["edicao", "comando", "edicao"]


def test_comando_malformado_aborta_preparacao(tmp_path):
    """Comando sem 'comando' válido gera erro fatal e nada é preparado nem gravado."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    (projeto / "a.py").write_text("x = 1\n", encoding="utf-8")
    plano = {"operacoes": [
        {"acao": "arquivo", "arquivo": "a.py", "codigo_id": "b1"},
        {"acao": "comando", "comando": "   "}]}   # comando vazio
    blocos = "```python\n# --- id=b1 ---\nx = 2\n```\n"
    r, p = _resposta(tmp_path, plano, blocos)
    res = aplicador.executar(r, p, aplicar=True, diff_path_str=None, sem_backup=True)
    assert res.sucesso is False
    assert res.sequenciado is True
    assert res.erros and any("comando" in e for e in res.erros)
    assert (Path(p) / "a.py").read_text(encoding="utf-8") == "x = 1\n"  # nada gravado
