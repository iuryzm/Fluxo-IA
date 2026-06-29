"""Testes do histórico de comandos. Isolados em tmp_path via monkeypatch."""
import pytest

from pyresumidor.core import armazenamento as arz


@pytest.fixture
def dados_tmp(tmp_path, monkeypatch):
    base = tmp_path / "dados"
    base.mkdir()
    monkeypatch.setattr(arz, "diretorio_dados", lambda: base)
    return base


@pytest.fixture
def gitignore(tmp_path):
    raiz = tmp_path / "Proj"
    raiz.mkdir()
    g = raiz / ".gitignore"
    g.write_text("*\n!.gitignore\n", encoding="utf-8")
    return str(g)


def test_historico_vazio_quando_novo(dados_tmp, gitignore):
    assert arz.listar_historico(gitignore) == []


def test_registra_e_lista(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 42})
    hist = arz.listar_historico(gitignore)
    assert len(hist) == 1
    assert hist[0]["comando"] == "mapear"
    assert hist[0]["ok"] is True
    assert hist[0]["resumo"]["total_linhas"] == 42


def test_mais_recente_no_topo(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "mapear", True, {})
    arz.registrar_historico(gitignore, "extrair", True, {})
    hist = arz.listar_historico(gitignore)
    assert hist[0]["comando"] == "extrair"  # último registrado no topo


def test_historico_nao_apaga_outros_campos(dados_tmp, gitignore):
    # registrar histórico deve fazer MERGE, preservando o resto do projeto.json
    arz.salvar_projeto(gitignore, {"nome": "Proj", "gitignore": gitignore})
    arz.registrar_historico(gitignore, "mapear", True, {})
    proj = arz.carregar_projeto(gitignore)
    assert proj["nome"] == "Proj"          # campo anterior preservado
    assert len(proj["historico"]) == 1     # histórico anexado


def test_historico_respeita_teto(dados_tmp, gitignore):
    arz.salvar_config({"max_historico": 3})
    for i in range(5):
        arz.registrar_historico(gitignore, "mapear", True, {"i": i})
    hist = arz.listar_historico(gitignore)
    assert len(hist) == 3                   # truncado
    assert hist[0]["resumo"]["i"] == 4      # mantém os mais recentes


def test_config_padrao_inclui_max_historico(dados_tmp):
    assert arz.carregar_config()["max_historico"] == 50
