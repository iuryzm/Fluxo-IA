"""Modelo de projeto.

A fonte de verdade do caminho é o .gitignore (é o que o core consome). A raiz é
DERIVADA dele (seu diretório-pai), então nunca há dois campos podendo divergir.
Será expandido na Fase 4 com exclusões, histórico de comandos e estatísticas.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Projeto:
    nome: str
    gitignore: str | None = None  # caminho do .gitignore; definido na página Identificar

    @property
    def raiz(self) -> str | None:
        """Diretório-raiz do projeto: o pai do .gitignore (o core usa .parent)."""
        if not self.gitignore:
            return None
        return str(Path(self.gitignore).resolve().parent)
