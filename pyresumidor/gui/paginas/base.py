"""Base das páginas de operação.

A janela troca o Projeto corrente ao mudar de aba e chama definir_projeto em
cada página; a página se redesenha em atualizar(). O cabeçalho/descrição vêm dos
atributos de classe, então cada página concreta só declara titulo e descricao.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QDialog,
    QTextEdit,
    QPushButton,
)
from PySide6.QtGui import (
    QFont,
)


class PaginaBase(QWidget):
    titulo = "Página"
    descricao = ""

    # Emitido quando uma página altera o nome do projeto corrente; a janela
    # escuta para renomear a aba ativa (a página não toca a QTabBar diretamente).
    projeto_renomeado = Signal()

    def __init__(self):
        super().__init__()
        self._projeto = None

        layout = QVBoxLayout(self)
        cabecalho = QLabel(f"<h2>{self.titulo}</h2>")
        desc = QLabel(self.descricao)
        desc.setWordWrap(True)
        self._estado = QLabel("Nenhum projeto selecionado.")
        self._estado.setWordWrap(True)

        layout.addWidget(cabecalho)
        layout.addWidget(desc)
        layout.addWidget(self._estado)
        layout.addStretch(1)

    def definir_projeto(self, projeto):
        self._projeto = projeto
        self.atualizar()

    def atualizar(self):
        """Reflete o projeto corrente. As páginas concretas podem sobrescrever
        para mostrar campos/controles próprios (Fase 3)."""
        if self._projeto is None:
            self._estado.setText("Nenhum projeto selecionado.")
        else:
            raiz = self._projeto.raiz or "(raiz ainda não definida)"
            self._estado.setText(f"Projeto: <b>{self._projeto.nome}</b> · raiz: {raiz}")

    def _mostrar_ajuda(self, titulo: str, texto: str):
        """Abre um diálogo de ajuda read-only com `texto` em fonte monoespaçada.

        Helper compartilhado pelas páginas (Extrair/Aplicar) para exibir exemplos de
        formato. O texto é selecionável e copiável — o usuário pode usar o exemplo como
        ponto de partida. Diálogo próprio (não QMessageBox) para comportar exemplos
        longos com scroll e formatação de código legível.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(titulo)
        dlg.resize(640, 480)
        lay = QVBoxLayout(dlg)

        visor = QTextEdit()
        visor.setReadOnly(True)
        visor.setFont(QFont("Consolas", 9))
        visor.setPlainText(texto)
        lay.addWidget(visor)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(dlg.accept)
        lay.addWidget(fechar)

        dlg.exec()
