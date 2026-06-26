"""Testes de mapear: contrato Resultado*, contagem de linhas, exclusão, erro-como-dado."""
from pyresumidor.core import mapear


def test_mapear_retorna_resultado_sucesso(gitignore, tmp_path):
    saida = tmp_path / "mapa.md"
    res = mapear.mapear_repositorio(str(gitignore), str(saida))
    assert res.sucesso is True
    assert saida.exists()
    assert res.caminho_saida is not None
    # exemplo.py entra como .py; config.yaml como "outro"
    assert any(p.endswith("exemplo.py") for p in res.arquivos_py)
    assert any(p.endswith("config.yaml") for p in res.arquivos_outros)


def test_mapear_conta_linhas(gitignore, tmp_path):
    saida = tmp_path / "mapa.md"
    res = mapear.mapear_repositorio(str(gitignore), str(saida))
    # total_linhas é a soma de linhas_por_arquivo (insumo do grafico de evolucao)
    assert res.total_linhas == sum(res.linhas_por_arquivo.values())
    assert res.total_linhas > 0
    # cada arquivo mapeado tem uma contagem
    assert all(v >= 0 for v in res.linhas_por_arquivo.values())


def test_mapear_gitignore_ausente_vira_erro(tmp_path):
    # Sem sys.exit: arquivo inexistente deve voltar como sucesso=False + erros
    fantasma = tmp_path / "nao_existe" / ".gitignore"
    saida = tmp_path / "mapa.md"
    res = mapear.mapear_repositorio(str(fantasma), str(saida))
    assert res.sucesso is False
    assert res.erros
    assert not saida.exists()


def test_mapear_exclusao_remove_arquivo(gitignore, tmp_path):
    saida = tmp_path / "mapa.md"
    res = mapear.mapear_repositorio(str(gitignore), str(saida), excluir=["exemplo.py"])
    # excluido do resumo: nao aparece em arquivos_py
    assert not any(p.endswith("exemplo.py") for p in res.arquivos_py)
