"""Testes da agregação de estatísticas. Isolados em tmp_path via monkeypatch."""
import pytest

from pyresumidor.core import armazenamento as arz
from pyresumidor.core import estatisticas as est
from pyresumidor.core.resultados import (
    ResultadoMapear,
    ResultadoAplicar,
    ResultadoArquivoAplicado,
)


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


def test_resumo_historico_mapear_inclui_por_arquivo():
    """resumo_historico() do Mapear mantém os agregados legados e adiciona o
    breakdown linhas_por_arquivo, pronto para gravar no histórico."""
    res = ResultadoMapear(
        sucesso=True, conteudo="x", caminho_saida=None,
        arquivos_py=["a.py", "b.py"], arquivos_outros=["c.toml"],
        linhas_por_arquivo={"a.py": 10, "b.py": 5, "c.toml": 3},
        total_linhas=18, copiado=False)
    r = res.resumo_historico()
    assert r["total_linhas"] == 18
    assert r["n_py"] == 2
    assert r["n_outros"] == 1
    assert r["linhas_por_arquivo"] == {"a.py": 10, "b.py": 5, "c.toml": 3}


def test_resumo_historico_aplicar_inclui_por_arquivo():
    """resumo_historico(gravados) do Aplicar inclui só arquivos com diff no
    breakdown por_arquivo, no formato {rel: {"add", "rem"}}."""
    arqs = [
        ResultadoArquivoAplicado(caminho="a.py", adicionadas=7, removidas=2,
                                 diff="diff...", gravado=True, backup_criado=False),
        ResultadoArquivoAplicado(caminho="sem_diff.py", adicionadas=0, removidas=0,
                                 diff="", gravado=False, backup_criado=False),
    ]
    res = ResultadoAplicar(
        sucesso=True, aplicado=True, arquivos=arqs,
        total_adicionadas=7, total_removidas=2,
        caminho_patch=None, caminho_html=None)
    r = res.resumo_historico(gravados=1)
    assert r["gravados"] == 1
    assert r["adicionadas"] == 7
    assert r["removidas"] == 2
    assert r["por_arquivo"] == {"a.py": {"add": 7, "rem": 2}}  # sem_diff.py fora
    assert "sem_diff.py" not in r["por_arquivo"]


def test_calcular_extrai_breakdown_mapear_recente(dados_tmp, gitignore):
    """calcular expõe ultimo_mapa_por_arquivo a partir do Mapear mais recente."""
    from pyresumidor.core.estatisticas import calcular
    arz.registrar_historico(
        gitignore, "mapear", True,
        {"total_linhas": 20, "n_py": 1, "n_outros": 0,
         "linhas_por_arquivo": {"antigo.py": 20}})
    arz.registrar_historico(
        gitignore, "mapear", True,
        {"total_linhas": 33, "n_py": 2, "n_outros": 0,
         "linhas_por_arquivo": {"a.py": 30, "b.py": 3}})
    s = calcular(gitignore)
    # O mais recente vence (hist é decrescente).
    assert s.ultimo_mapa_por_arquivo == {"a.py": 30, "b.py": 3}


def test_calcular_extrai_breakdown_aplicar_recente(dados_tmp, gitignore):
    """calcular expõe ultimo_aplicar_por_arquivo do Aplicar mais recente, sem se
    confundir com um mapear registrado depois."""
    from pyresumidor.core.estatisticas import calcular
    arz.registrar_historico(
        gitignore, "aplicar", True,
        {"gravados": 1, "adicionadas": 5, "removidas": 1, "aplicado": True,
         "por_arquivo": {"x.py": {"add": 5, "rem": 1}}})
    # Um mapear posterior não deve apagar o breakdown do último aplicar.
    arz.registrar_historico(
        gitignore, "mapear", True,
        {"total_linhas": 9, "n_py": 1, "n_outros": 0,
         "linhas_por_arquivo": {"x.py": 9}})
    s = calcular(gitignore)
    assert s.ultimo_aplicar_por_arquivo == {"x.py": {"add": 5, "rem": 1}}


def test_calcular_fallback_registro_antigo_sem_breakdown(dados_tmp, gitignore):
    """Registro antigo (sem linhas_por_arquivo / por_arquivo) é lido sem quebrar:
    os agregados continuam somando e os breakdowns ficam {}."""
    from pyresumidor.core.estatisticas import calcular
    arz.registrar_historico(
        gitignore, "aplicar", True,
        {"gravados": 1, "adicionadas": 4, "removidas": 0, "aplicado": True})
    arz.registrar_historico(
        gitignore, "mapear", True,
        {"total_linhas": 12, "n_py": 1, "n_outros": 0})
    s = calcular(gitignore)
    assert s.total_adicionadas == 4          # agregado legado ainda soma
    assert s.ultimo_mapa_por_arquivo == {}   # ausente -> vazio, sem erro
    assert s.ultimo_aplicar_por_arquivo == {}
