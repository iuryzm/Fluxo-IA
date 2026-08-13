"""Testes da extração por fatia (trechos parciais): parser de fatia e processar_trecho.

Cobrem o caminho de `trechos` do extrator, que nasceu sem cobertura — mesmo tipo de
buraco que já deixou uma inserção mal posicionada passar no pytest. Auto-contidos:
escrevem o arquivo-alvo em tmp_path, sem depender de fixtures do conftest.
"""
from pathlib import Path
from pyresumidor.core import extrator


# --- _parsear_fatia -------------------------------------------------------------

def test_parsear_fatia_primeiras_ok():
    lado, n, erro = extrator._parsear_fatia("primeiras:5")
    assert (lado, n, erro) == ("primeiras", 5, None)


def test_parsear_fatia_ultimas_ok():
    lado, n, erro = extrator._parsear_fatia("ultimas:10")
    assert (lado, n, erro) == ("ultimas", 10, None)


def test_parsear_fatia_maiuscula_e_espaco_normaliza():
    """Lado é normalizado (case/trim); N com espaço ao redor também."""
    lado, n, erro = extrator._parsear_fatia("  PRIMEIRAS : 3 ")
    assert (lado, n, erro) == ("primeiras", 3, None)


def test_parsear_fatia_sem_dois_pontos_vira_erro():
    lado, n, erro = extrator._parsear_fatia("primeiras5")
    assert lado is None and n is None and erro is not None


def test_parsear_fatia_lado_invalido_vira_erro():
    lado, n, erro = extrator._parsear_fatia("meio:3")
    assert lado is None and erro is not None


def test_parsear_fatia_n_zero_ou_negativo_vira_erro():
    for ruim in ("primeiras:0", "ultimas:-2", "primeiras:"):
        lado, n, erro = extrator._parsear_fatia(ruim)
        assert lado is None and erro is not None, ruim


# --- processar_trecho -----------------------------------------------------------

_FONTE = '''\
import os
from pathlib import Path


class Motor:
    def run(self):
        a = 1
        b = 2
        c = 3
        return a + b + c


def solta():
    x = 10
    return x
'''


def _escreve(tmp_path):
    alvo = tmp_path / "mod.py"
    alvo.write_text(_FONTE, encoding="utf-8")
    return alvo


def test_processar_trecho_primeiras_do_arquivo(tmp_path):
    """Sem alvo: fatia relativa ao arquivo inteiro (caso 'imports do topo')."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, None, "primeiras:2")
    assert encontrado is True
    assert "import os" in md
    assert "from pathlib import Path" in md
    assert "class Motor" not in md          # cortou antes da classe
    assert "RECORTE PARCIAL" in md          # é recorte: sobrou coisa de fora


def test_processar_trecho_primeiras_de_metodo(tmp_path):
    """Com alvo Classe.metodo: fatia conta as linhas do span do nó."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, "Motor.run", "primeiras:1")
    assert encontrado is True
    assert "def run(self):" in md           # 1ª linha do método
    assert "return a + b + c" not in md     # não chegou ao fim
    assert "RECORTE PARCIAL" in md


def test_processar_trecho_ultimas_de_funcao(tmp_path):
    """ultimas:N pega a cauda do nó (útil para ver o return / final)."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, "solta", "ultimas:1")
    assert encontrado is True
    assert "return x" in md
    assert "def solta" not in md            # cortou o começo
    assert "RECORTE PARCIAL" in md


def test_processar_trecho_n_maior_que_alvo_cobre_tudo(tmp_path):
    """N >= tamanho do alvo devolve tudo e NÃO marca recorte parcial."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, "solta", "primeiras:99")
    assert encontrado is True
    assert "def solta" in md and "return x" in md
    assert "RECORTE PARCIAL" not in md
    assert "cobre tudo" in md


def test_processar_trecho_alvo_inexistente_marca_nao_encontrado(tmp_path):
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, "NaoExiste.foo", "primeiras:3")
    assert encontrado is False
    assert aviso is not None
    assert "não encontrado" in aviso


def test_processar_trecho_fatia_malformada_erro_como_dado(tmp_path):
    """Fatia inválida não levanta: vira markdown de aviso + encontrado=False."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, None, "xyz:3")
    assert encontrado is False
    assert aviso is not None
    assert "inválida" in aviso


def test_processar_trecho_constante_de_modulo_encontrada(tmp_path):
    """Alvo é uma CONSTANTE de módulo (Assign simples): span cobre a atribuição inteira."""
    fonte = (
        "import os\n"
        "\n"
        "LIMITE = 5\n"
        "\n"
        "def solta():\n"
        "    return LIMITE\n"
    )
    alvo = tmp_path / "mod_constante.py"
    alvo.write_text(fonte, encoding="utf-8")
    md, encontrado, aviso = extrator.processar_trecho(alvo, "LIMITE", "primeiras:1")
    assert encontrado is True
    assert "LIMITE = 5" in md
    assert "RECORTE PARCIAL" not in md      # 1 linha pedida == 1 linha do span: cobre tudo


def test_processar_trecho_constante_ann_assign_sem_valor_nao_casa(tmp_path):
    """AnnAssign sem valor (só anotação, ex. 'x: int') não tem conteúdo: não casa como alvo."""
    fonte = (
        "LIMITE: int\n"
        "\n"
        "def f():\n"
        "    return 1\n"
    )
    alvo = tmp_path / "mod_anotacao.py"
    alvo.write_text(fonte, encoding="utf-8")
    md, encontrado, aviso = extrator.processar_trecho(alvo, "LIMITE", "primeiras:1")
    assert encontrado is False
    assert aviso is not None
    assert "não encontrado" in aviso


def test_processar_trecho_constante_simples_inexistente_nao_encontrada(tmp_path):
    """Nome que não é função, classe nem constante de módulo: erro-como-dado, sem exceção."""
    alvo = _escreve(tmp_path)
    md, encontrado, aviso = extrator.processar_trecho(alvo, "NAO_EXISTE", "primeiras:1")
    assert encontrado is False
    assert aviso is not None
    assert "não encontrado" in aviso
