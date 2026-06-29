"""Testes da camada de persistência (armazenamento). Isolados em tmp_path via
monkeypatch — nunca tocam a pasta dados/ real do pacote."""
import pytest

from pyresumidor.core import armazenamento as arz


@pytest.fixture
def dados_tmp(tmp_path, monkeypatch):
    """Redireciona diretorio_dados() para um tmp_path descartável por teste."""
    base = tmp_path / "dados"
    base.mkdir()
    monkeypatch.setattr(arz, "diretorio_dados", lambda: base)
    return base


@pytest.fixture
def gitignore(tmp_path):
    """Um .gitignore real em disco (registrar_recente/listar resolve caminho real)."""
    raiz = tmp_path / "MeuProjeto"
    raiz.mkdir()
    g = raiz / ".gitignore"
    g.write_text("*\n!.gitignore\n", encoding="utf-8")
    return str(g)


def test_config_padrao_quando_ausente(dados_tmp):
    cfg = arz.carregar_config()
    assert cfg["max_recentes"] == 10


def test_config_salva_e_relê(dados_tmp):
    arz.salvar_config({"max_recentes": 3})
    assert arz.carregar_config()["max_recentes"] == 3


def test_config_corrompido_cai_no_padrao(dados_tmp):
    arz.caminho_config().write_text("{ isto nao e json", encoding="utf-8")
    # não quebra: devolve padrão
    assert arz.carregar_config()["max_recentes"] == 10


def test_projeto_salva_e_carrega(dados_tmp, gitignore):
    arz.salvar_projeto(gitignore, {"nome": "MeuProjeto", "gitignore": gitignore})
    lido = arz.carregar_projeto(gitignore)
    assert lido["nome"] == "MeuProjeto"


def test_projeto_inexistente_devolve_vazio(dados_tmp, gitignore):
    assert arz.carregar_projeto(gitignore) == {}


def test_recente_registra_e_lista(dados_tmp, gitignore):
    arz.registrar_recente(gitignore, "MeuProjeto")
    recentes = arz.listar_recentes()
    assert len(recentes) == 1
    assert recentes[0]["nome"] == "MeuProjeto"


def test_recente_nao_duplica_sobe_ao_topo(dados_tmp, tmp_path):
    g1 = tmp_path / "P1"; g1.mkdir(); (g1 / ".gitignore").write_text("*\n", encoding="utf-8")
    g2 = tmp_path / "P2"; g2.mkdir(); (g2 / ".gitignore").write_text("*\n", encoding="utf-8")
    arz.registrar_recente(str(g1 / ".gitignore"), "P1")
    arz.registrar_recente(str(g2 / ".gitignore"), "P2")
    arz.registrar_recente(str(g1 / ".gitignore"), "P1")  # repete P1
    recentes = arz.listar_recentes()
    assert len(recentes) == 2          # não duplicou
    assert recentes[0]["nome"] == "P1"  # voltou ao topo


def test_recente_respeita_teto(dados_tmp, tmp_path):
    arz.salvar_config({"max_recentes": 2})
    for i in range(4):
        d = tmp_path / f"P{i}"; d.mkdir()
        (d / ".gitignore").write_text("*\n", encoding="utf-8")
        arz.registrar_recente(str(d / ".gitignore"), f"P{i}")
    assert len(arz.listar_recentes()) == 2  # truncado em 2


def test_recente_filtra_gitignore_inexistente(dados_tmp, tmp_path):
    d = tmp_path / "Some"; d.mkdir()
    g = d / ".gitignore"; g.write_text("*\n", encoding="utf-8")
    arz.registrar_recente(str(g), "Some")
    g.unlink()  # arquivo some (faxina da VM)
    assert arz.listar_recentes() == []  # não oferece projeto que sumiu
