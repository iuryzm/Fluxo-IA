"""Página Identificar: aponta o .gitignore do projeto, valida e o grava no Projeto.

O PyResumidor usa o .gitignore como ALLOWLIST: a varredura parte das linhas de
negação (`!arquivo`), não de um scan da pasta. Por isso a validação aqui checa que
o arquivo existe e tem ao menos uma negação — sem isso o mapa sai vazio. Quantas
dessas negações casam de fato com arquivos reais é o Mapear quem dirá (globar o
projeto aqui travaria a UI; é trabalho de worker, na próxima fase).
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit, QFileDialog,
    QMessageBox,
)

from pyresumidor.gui.paginas.base import PaginaBase

_AJUDA = """\
<h3>Como deve ser o .gitignore do PyResumidor</h3>
<p>O PyResumidor <b>não</b> varre a pasta atrás de arquivos. Ele usa o
<code>.gitignore</code> como uma <b>lista de permissão</b> (allowlist): primeiro
ignora tudo, depois você <b>readiciona</b> só o que o mapa deve incluir, com
linhas começando por <code>!</code>.</p>

<p>Exemplo mínimo:</p>
<pre>*

!.gitignore
!src/app.py
!src/util.py
!config.yaml</pre>

<p>Lendo de cima para baixo:</p>
<ul>
<li><code>*</code> — ignora tudo.</li>
<li><code>!src/app.py</code> — readiciona esse arquivo ao mapa (uma linha por arquivo).</li>
</ul>

<p>Para projetos com subpastas, deixe o git descer nelas com uma linha de pasta
(o PyResumidor a ignora de propósito, pois termina em <code>/</code>):</p>
<pre>*
!*/
!src/app.py
!src/sub/outro.py</pre>

<p><b>Sem nenhuma linha <code>!</code></b>, nada é readicionado e o mapa sai
vazio — é o aviso que aparece ao selecionar um arquivo sem negações.</p>
"""


class PaginaIdentificar(PaginaBase):
    titulo = "Identificar Projeto"
    descricao = ("Aponte o arquivo .gitignore do projeto. Ele define quais arquivos "
                 "entram no mapa (modelo de allowlist — veja a ajuda).")

    def __init__(self):
        super().__init__()
        layout = self.layout()
        idx = layout.indexOf(self._estado) + 1

        # Dropdown de projetos recentes (acima do campo). Populado só em momentos
        # controlados (__init__/atualizar) com sinais bloqueados — nunca dentro de
        # _definir_gitignore, para não disparar seleção durante o registro.
        self._combo = QComboBox()
        self._combo.activated.connect(self._on_recente)

        linha = QHBoxLayout()
        self._campo = QLineEdit()
        self._campo.setPlaceholderText("Caminho do .gitignore…")
        self._campo.setReadOnly(True)
        botao_procurar = QPushButton("Procurar…")
        botao_procurar.clicked.connect(self._procurar)
        botao_ajuda = QPushButton("?")
        botao_ajuda.setFixedWidth(32)
        botao_ajuda.setToolTip("Como deve ser o .gitignore")
        botao_ajuda.clicked.connect(self._mostrar_ajuda)
        linha.addWidget(self._campo, 1)
        linha.addWidget(botao_procurar, 0)
        linha.addWidget(botao_ajuda, 0)

        self._validacao = QLabel("")
        self._validacao.setWordWrap(True)

        container = QVBoxLayout()
        container.addWidget(self._combo)
        container.addLayout(linha)
        container.addWidget(self._validacao)
        layout.insertLayout(idx, container)

        self._popular_recentes()

    def _popular_recentes(self):
        """Recarrega o dropdown a partir de listar_recentes(). Sinais bloqueados
        para o preenchimento não disparar _on_recente. Desabilitado se vazio."""
        from pyresumidor.core.armazenamento import listar_recentes
        recentes = listar_recentes()
        self._combo.blockSignals(True)
        self._combo.clear()
        if recentes:
            self._combo.addItem("— selecione um projeto recente —", userData=None)
            for e in recentes:
                rotulo = f"{e.get('nome', '?')}  ({e.get('gitignore', '')})"
                self._combo.addItem(rotulo, userData=e.get("gitignore"))
            self._combo.setEnabled(True)
        else:
            self._combo.addItem("— nenhum projeto recente —", userData=None)
            self._combo.setEnabled(False)
        self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def _on_recente(self, indice):
        caminho = self._combo.itemData(indice)
        if caminho:
            self._definir_gitignore(caminho)
        # volta o combo ao placeholder (a seleção já virou o campo)
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def _procurar(self):
        inicio = self._projeto.raiz if (self._projeto and self._projeto.raiz) else ""
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecione o .gitignore", inicio,
            "gitignore (.gitignore);;Todos os arquivos (*)")
        if caminho:
            self._definir_gitignore(caminho)

    def _definir_gitignore(self, caminho):
        if self._projeto is None:
            return
        self._projeto.gitignore = caminho
        from pathlib import Path as _P
        nome_pasta = _P(caminho).resolve().parent.name
        if nome_pasta:
            self._projeto.nome = nome_pasta
            self.projeto_renomeado.emit()
        self._campo.setText(caminho)
        self._validar(caminho)
        # Registra como recente (estado persistido). Usa o nome já calculado.
        from pyresumidor.core.armazenamento import registrar_recente
        try:
            registrar_recente(caminho, nome_pasta or "projeto")
        except Exception:
            pass  # registro de recente nunca deve quebrar a identificação
        PaginaBase.atualizar(self)

    def _validar(self, caminho):
        p = Path(caminho)
        if not p.exists():
            self._validacao.setText("<span style='color:#c0392b'>❌ Arquivo não encontrado.</span>")
            return
        self._validacao.setText("⏳ Validando…")
        QApplication.processEvents()
        try:
            linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            self._validacao.setText(f"<span style='color:#c0392b'>❌ Não consegui ler: {e}</span>")
            return
        negacoes = [l.strip() for l in linhas
                    if l.strip().startswith("!") and not l.strip().endswith("/")]
        if negacoes:
            self._validacao.setText(
                f"<span style='color:#27ae60'>✅ {len(negacoes)} arquivo(s) na allowlist.</span> "
                "Quantos existem de fato, o Mapear dirá.")
        else:
            self._validacao.setText(
                "<span style='color:#d35400'>⚠️ Nenhuma linha de negação (<code>!arquivo</code>). "
                "O mapa sairá vazio — veja a ajuda (?) para o formato correto.</span>")

    def _mostrar_ajuda(self):
        cx = QMessageBox(self)
        cx.setWindowTitle("Formato do .gitignore")
        cx.setTextFormat(Qt.TextFormat.RichText)
        cx.setText(_AJUDA)
        cx.exec()

    def atualizar(self):
        super().atualizar()
        if hasattr(self, "_campo"):
            atual = self._projeto.gitignore if (self._projeto and self._projeto.gitignore) else ""
            self._campo.setText(atual or "")
            if atual:
                self._validar(atual)
            else:
                self._validacao.setText("")
            # repopula recentes ao trocar de aba (pode ter mudado noutra aba)
            if hasattr(self, "_combo"):
                self._popular_recentes()
