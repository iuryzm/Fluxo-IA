"""Cria o QApplication e abre a janela principal."""
import sys

from PySide6.QtWidgets import QApplication

from pyresumidor.gui.janela import JanelaPrincipal


def iniciar() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()
