"""Janela principal.

Abas de projeto (topo) + menu lateral de operações + QStackedWidget de páginas,
todos COMPARTILHADOS. Trocar de aba não recria nada: só troca qual Projeto as
páginas leem. Trocar de item no menu lateral só troca a página visível no stack.
"""
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabBar, QToolButton,
    QPushButton, QStackedWidget, QButtonGroup,
)

from pyresumidor.gui.modelos import Projeto
from pyresumidor.gui.paginas import (
    PaginaIdentificar, PaginaMapear, PaginaExtrair, PaginaAplicar,
)


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyResumidor")
        self.resize(900, 600)

        self._projetos = []        # paralelo às abas: índice da aba -> Projeto
        self._contador_novos = 0   # numera os projetos criados

        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)

        # --- Barra de abas de projeto (com + para adicionar e × para fechar) ---
        linha_abas = QHBoxLayout()
        self._abas = QTabBar()
        self._abas.setTabsClosable(True)
        self._abas.setMovable(True)
        self._abas.setExpanding(False)
        self._abas.currentChanged.connect(self._on_aba_mudou)
        self._abas.tabCloseRequested.connect(self._on_fechar_aba)

        botao_add = QToolButton()
        botao_add.setText("+")
        botao_add.setToolTip("Novo projeto")
        botao_add.clicked.connect(self.novo_projeto)

        linha_abas.addWidget(self._abas, 1)
        linha_abas.addWidget(botao_add, 0)
        raiz.addLayout(linha_abas)

        # --- Corpo: menu lateral + stack de páginas ---
        corpo = QHBoxLayout()
        raiz.addLayout(corpo, 1)

        self._paginas = [
            PaginaIdentificar(),
            PaginaMapear(),
            PaginaExtrair(),
            PaginaAplicar(),
        ]
        self._stack = QStackedWidget()
        for p in self._paginas:
            self._stack.addWidget(p)

        # menu lateral: um botão por página, exclusivo, alterna o stack
        coluna_menu = QWidget()
        coluna_menu.setFixedWidth(180)
        menu = QVBoxLayout(coluna_menu)
        self._grupo_menu = QButtonGroup(self)
        self._grupo_menu.setExclusive(True)
        for i, p in enumerate(self._paginas):
            b = QPushButton(p.titulo)
            b.setCheckable(True)
            self._grupo_menu.addButton(b, i)
            menu.addWidget(b)
        menu.addStretch(1)
        self._grupo_menu.idClicked.connect(self._stack.setCurrentIndex)
        self._grupo_menu.button(0).setChecked(True)

        corpo.addWidget(coluna_menu, 0)
        corpo.addWidget(self._stack, 1)

        # abre um projeto inicial
        self.novo_projeto()

    # ---- projetos / abas ----
    @Slot()
    def novo_projeto(self):
        self._contador_novos += 1
        projeto = Projeto(nome=f"Projeto {self._contador_novos}")
        self._projetos.append(projeto)
        idx = self._abas.addTab(projeto.nome)
        self._abas.setCurrentIndex(idx)

    @Slot(int)
    def _on_aba_mudou(self, indice):
        projeto = self._projetos[indice] if 0 <= indice < len(self._projetos) else None
        for p in self._paginas:
            p.definir_projeto(projeto)

    @Slot(int)
    def _on_fechar_aba(self, indice):
        if not (0 <= indice < len(self._projetos)):
            return
        del self._projetos[indice]
        self._abas.removeTab(indice)
        if not self._projetos:      # nunca deixa a janela sem projeto
            self.novo_projeto()
