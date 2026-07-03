"""Testes do confirmador de terminal da CLI (a decisão de segurança do opt-in).

Foco: a LÓGICA de confirmação — sem TTY recusa; com TTY, resposta 's' aprova e o resto
recusa; modo lote decide uma vez para todos. O parsing de argumentos e o render não são
testados aqui (baixo valor, alto atrito — exercitados rodando a CLI de verdade).
"""
import builtins
import pytest
from pyresumidor.cli.main import _confirmador_terminal
from pyresumidor.core.resultados import PassoComando


def _pc(comando="echo x", **kw):
    return PassoComando(comando=comando, **kw)


def test_sem_tty_recusa(monkeypatch):
    """stdin não-interativo: recusa tudo, sem sequer perguntar."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    conf = _confirmador_terminal(lote=False, todos_comandos=[_pc()])
    assert conf(_pc()) is False


def test_um_a_um_sim_aprova(monkeypatch):
    """TTY + resposta 's': aprova aquele comando."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _="": "s")
    conf = _confirmador_terminal(lote=False, todos_comandos=[])
    assert conf(_pc()) is True


def test_um_a_um_nao_recusa(monkeypatch):
    """TTY + resposta vazia (default N): recusa."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _="": "")
    conf = _confirmador_terminal(lote=False, todos_comandos=[])
    assert conf(_pc()) is False


def test_lote_aprova_todos(monkeypatch):
    """TTY + lote + 's': um único sim aprova todos os comandos."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _="": "sim")
    conf = _confirmador_terminal(lote=True, todos_comandos=[_pc("a"), _pc("b")])
    assert conf(_pc("a")) is True
    assert conf(_pc("b")) is True


def test_lote_recusa_todos(monkeypatch):
    """TTY + lote + 'n': um único não recusa todos."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _="": "n")
    conf = _confirmador_terminal(lote=True, todos_comandos=[_pc("a"), _pc("b")])
    assert conf(_pc("a")) is False
    assert conf(_pc("b")) is False
