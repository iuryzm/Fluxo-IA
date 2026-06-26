"""Página Extrair (stub da Fase 2)."""
from pyresumidor.gui.paginas.base import PaginaBase


class PaginaExtrair(PaginaBase):
    titulo = "Extrair"
    descricao = ("Recebe o JSON da IA e extrai as classes/funções pedidas, "
                 "anexando as instruções do aplicador. (Backend na Fase 3.)")
