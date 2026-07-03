"""Testes da supressão das instruções do aplicador na saída do Extrair.

Cobrem a precedência OR entre a flag da CLI (incluir_instrucoes) e a chave
"sem_instrucoes" do JSON da IA: as instruções só são anexadas quando AMBAS
permitem. Auto-contidos: escrevem resposta-JSON e projeto em tmp_path.
"""
import json
from pathlib import Path
from pyresumidor.core import extrator


def _monta(tmp_path, requisicoes: dict):
    """Grava a resposta-JSON e devolve (resposta_path, projeto_path, saida_path)."""
    projeto = tmp_path / "proj"
    projeto.mkdir()
    resposta = tmp_path / "resposta.json"
    resposta.write_text(json.dumps(requisicoes), encoding="utf-8")
    saida = tmp_path / "saida.md"
    return str(resposta), str(projeto), str(saida)


def test_instrucoes_anexadas_por_padrao(tmp_path):
    """Flag CLI liga (default) e IA não pede omissão: instruções anexadas."""
    r, p, s = _monta(tmp_path, {"arquivos_completos": []})
    res = extrator.executar_extracao(r, p, s, incluir_instrucoes=True)
    assert res.sucesso is True
    assert res.instrucoes_anexadas is True


def test_ia_pede_sem_instrucoes_suprime(tmp_path):
    """IA manda 'sem_instrucoes': true — suprime mesmo com a flag CLI ligada."""
    r, p, s = _monta(tmp_path, {"arquivos_completos": [], "sem_instrucoes": True})
    res = extrator.executar_extracao(r, p, s, incluir_instrucoes=True)
    assert res.instrucoes_anexadas is False
    # O motivo fica rastreável nos avisos.
    assert any("sem_instrucoes" in a for a in res.avisos)


def test_flag_cli_suprime_mesmo_sem_pedido_da_ia(tmp_path):
    """Flag CLI desligada suprime, independentemente da IA."""
    r, p, s = _monta(tmp_path, {"arquivos_completos": []})
    res = extrator.executar_extracao(r, p, s, incluir_instrucoes=False)
    assert res.instrucoes_anexadas is False


def test_valor_truthy_nao_booleano_nao_suprime(tmp_path):
    """'sem_instrucoes' só desliga com True de verdade: uma string truthy não conta."""
    r, p, s = _monta(tmp_path, {"arquivos_completos": [], "sem_instrucoes": "não"})
    res = extrator.executar_extracao(r, p, s, incluir_instrucoes=True)
    # "não" é truthy em Python, mas o guard é `is True` — logo NÃO suprime.
    assert res.instrucoes_anexadas is True
