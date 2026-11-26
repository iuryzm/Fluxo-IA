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
    QDialogButtonBox,
    QHBoxLayout,
    QStyle,
    QTextEdit,
    QPushButton,
)
from PySide6.QtGui import (
    QFont,
)
from pyresumidor.core import (
    clipboard,
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

    def _expandir(self, *widgets):
        """Faz `widgets` (campos de texto, diffs, gráficos) crescerem com a janela.

        O layout da página termina num addStretch(1) que, sozinho, absorveria todo o
        espaço vertical extra — os campos parariam no tamanho sugerido. Aqui os
        widgets recebem fator 1 e o espaçador final cai para 0: ele só ocupa espaço
        quando nenhum widget expansível estiver visível (mantendo o topo alinhado).
        """
        lay = self.layout()
        for w in widgets:
            lay.setStretchFactor(w, 1)
        lay.setStretch(lay.count() - 1, 0)

    def _confirmar(self, titulo: str, texto: str) -> bool:
        """Diálogo de confirmação Sim/Não para textos possivelmente longos.

        Substitui QMessageBox nas confirmações cujo conteúdo cresce com o plano
        (lista de arquivos/comandos): o QMessageBox cresce junto com o texto e pode
        empurrar os botões para fora da tela. Aqui o texto fica numa área rolável e o
        diálogo é limitado à área disponível da tela, então Sim/Não ficam sempre
        visíveis. 'Não' é o padrão (Enter/Esc não autorizam nada).
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(titulo)
        lay = QVBoxLayout(dlg)

        topo = QHBoxLayout()
        icone = QLabel()
        icone.setPixmap(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(32, 32))
        topo.addWidget(icone, 0)

        visor = QTextEdit()
        visor.setReadOnly(True)
        visor.setPlainText(texto)
        topo.addWidget(visor, 1)
        lay.addLayout(topo, 1)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        botoes.accepted.connect(dlg.accept)
        botoes.rejected.connect(dlg.reject)
        nao = botoes.button(QDialogButtonBox.StandardButton.No)
        nao.setDefault(True)
        nao.setFocus()
        lay.addWidget(botoes)

        # Tamanho: cabe o texto quando possível, mas nunca passa de ~80% da tela.
        tela = (self.screen() or dlg.screen()).availableGeometry()
        doc = visor.document()
        doc.setTextWidth(560)
        alt_texto = int(doc.size().height()) + 40
        largura = min(640, int(tela.width() * 0.8))
        altura = min(max(alt_texto + 80, 200), int(tela.height() * 0.8))
        dlg.resize(largura, altura)

        return dlg.exec() == QDialog.DialogCode.Accepted

    def _texto_plano_de_label(self, label: QLabel) -> str:
        """Converte o RichText (HTML simples: span/b/small/br) de um QLabel de aviso
        em texto plano, preservando quebras de linha e descartando tags/cores. Usado
        pelo botão 'Copiar aviso' — o usuário recebe o texto puro, sem marcação.
        """
        import re
        bruto = label.text()
        bruto = re.sub(r'(?i)<br\s*/?>', '\n', bruto)
        bruto = re.sub(r'<[^>]+>', '', bruto)
        return bruto.strip()

    def _copiar_aviso(self):
        """Copia o texto atual de `self._resultado` (avisos/status) para a área de
        transferência, em texto plano. Slot comum: páginas concretas que têm um QLabel
        `_resultado` e um botão `_botao_copiar_aviso` ligam o clique deste botão aqui.
        """
        texto = self._texto_plano_de_label(self._resultado)
        if not texto:
            return
        try:
            clipboard.copiar(texto)
            self._botao_copiar_aviso.setText("Copiado ✓")
        except Exception as e:
            self._resultado.setText(
                self._resultado.text() +
                f"<br><span style='color:#c0392b'>❌ Não consegui copiar: {e}</span>")
