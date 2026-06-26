"""Modelo de projeto.

Mínimo na Fase 2 (só o necessário para as abas trocarem de contexto). Será
expandido na Fase 4 com .gitignore/exclusões, histórico de comandos e estatísticas.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Projeto:
    nome: str
    raiz: str | None = None  # caminho-raiz; definido na página Identificar (Fase 3+)
