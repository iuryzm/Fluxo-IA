"""Testes da agregação de estatísticas. Isolados em tmp_path via monkeypatch."""
import pytest

from pyresumidor.core import armazenamento as arz
from pyresumidor.core import estatisticas as est


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


def test_projeto_sem_historico(dados_tmp, gitignore):
    s = est.calcular(gitignore)
    assert s.total_execucoes == 0
    assert s.por_comando == {}
    assert s.evolucao_linhas == []
    assert s.ultimo_mapa == {}


def test_conta_por_comando(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 100})
    arz.registrar_historico(gitignore, "extrair", True, {"itens": 2, "encontrados": 2})
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 120})
    s = est.calcular(gitignore)
    assert s.total_execucoes == 3
    assert s.por_comando["mapear"] == 2
    assert s.por_comando["extrair"] == 1


def test_soma_linhas_alteradas(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "aplicar", True, {"adicionadas": 10, "removidas": 4, "gravados": 1})
    arz.registrar_historico(gitignore, "aplicar", True, {"adicionadas": 5, "removidas": 2, "gravados": 1})
    s = est.calcular(gitignore)
    assert s.total_adicionadas == 15
    assert s.total_removidas == 6


def test_evolucao_em_ordem_cronologica(dados_tmp, gitignore):
    # registra fora de ordem de ts; evolucao deve sair ascendente
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 100})
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 150})
    s = est.calcular(gitignore)
    ts_vals = [ts for ts, _ in s.evolucao_linhas]
    assert ts_vals == sorted(ts_vals)              # cronológico
    linhas = [l for _, l in s.evolucao_linhas]
    assert linhas == [100, 150]                    # mais antigo primeiro


def test_ultimo_mapa_e_o_mais_recente(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 100, "n_py": 5})
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 200, "n_py": 8})
    s = est.calcular(gitignore)
    assert s.ultimo_mapa["total_linhas"] == 200    # o último registrado
    assert s.ultimo_mapa["n_py"] == 8


def test_extrair_nao_soma_linhas(dados_tmp, gitignore):
    # só aplicar conta para +/-; extrair/mapear não
    arz.registrar_historico(gitignore, "extrair", True, {"itens": 3, "encontrados": 1})
    s = est.calcular(gitignore)
    assert s.total_adicionadas == 0
    assert s.total_removidas == 0


def test_evolucao_arquivos(dados_tmp, gitignore):
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 100, "n_py": 5, "n_outros": 2})
    arz.registrar_historico(gitignore, "mapear", True, {"total_linhas": 150, "n_py": 6, "n_outros": 3})
    s = est.calcular(gitignore)
    arqs = [n for _, n in s.evolucao_arquivos]
    assert arqs == [7, 9]   # 5+2, depois 6+3, em ordem cronológica
