"""Página Mapear: roda mapear_repositorio num worker e mostra o ResultadoMapear.

O .md é gravado num caminho padrão dentro de dados/ (sobrevive à faxina da VM); o
produto principal do fluxo é o conteúdo copiado para o clipboard, pronto para colar
no chat da IA. O ResultadoMapear que chega no sinal já está no formato que a Fase 4
vai persistir como histórico.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QLabel

from pyresumidor.gui.paginas.base import PaginaBase
from pyresumidor.gui.workers import rodar_em_thread
from pyresumidor.core import mapear
from pyresumidor.core.armazenamento import caminho_mapa
from pyresumidor.core.armazenamento import caminho_mapa, registrar_historico
from pyresumidor.core import clipboard


class PaginaMapear(PaginaBase):
    titulo = "Mapear"
    descricao = ("Gera o resumo da arquitetura e o copia para colar no chat da IA. "
                 "Requer um .gitignore válido definido em Identificar.")

    def __init__(self):
        super().__init__()
        layout = self.layout()
        idx = layout.indexOf(self._estado) + 1

        self._botao = QPushButton("Mapear projeto")
        self._botao.clicked.connect(self._mapear)

        self._botao_copiar = QPushButton("Copiar mapa")
        self._botao_copiar.setEnabled(False)
        self._botao_copiar.clicked.connect(self._copiar)

        self._resultado = QLabel("")
        self._resultado.setWordWrap(True)
        self._resultado.setTextFormat(Qt.TextFormat.RichText)
        self._resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._botao_copiar_aviso = QPushButton("📋 Copiar aviso")
        self._botao_copiar_aviso.clicked.connect(self._copiar_aviso)

        layout.insertWidget(idx, self._botao)
        layout.insertWidget(idx + 1, self._botao_copiar)
        layout.insertWidget(idx + 2, self._resultado)
        layout.insertWidget(idx + 3, self._botao_copiar_aviso)

        self._conteudo_mapa = None  # guarda res.conteudo para o botão copiar

    def _mapear(self):
        # Botão sempre habilitado: a checagem de .gitignore vira aviso na tela.
        if self._projeto is None or not self._projeto.gitignore:
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ Defina um .gitignore válido na aba "
                "<b>Identificar Projeto</b> antes de mapear.</span>")
            return

        saida = caminho_mapa(self._projeto.gitignore)
        self._botao.setEnabled(False)
        self._botao_copiar.setEnabled(False)
        self._resultado.setText("⏳ Mapeando…")

        rodar_em_thread(
            self,
            mapear.mapear_repositorio,
            self._ao_concluir,
            self._ao_falhar,
            self._projeto.gitignore,   # caminho_gitignore_str
            str(saida),                # arquivo_saida_str
        )

    def _ao_concluir(self, res):
        self._botao.setEnabled(True)
        if not res.sucesso:
            erros = "<br>".join(res.erros) or "erro desconhecido"
            self._resultado.setText(f"<span style='color:#c0392b'>❌ {erros}</span>")
            return
        if not res.conteudo:
            avisos = "<br>".join(res.avisos) or "nada a mapear"
            self._resultado.setText(f"<span style='color:#d35400'>⚠️ {avisos}</span>")
            return

        self._conteudo_mapa = res.conteudo
        self._botao_copiar.setEnabled(True)
        try:
            registrar_historico(
                self._projeto.gitignore, "mapear", True, res.resumo_historico())
        except Exception:
            pass  # registro de histórico nunca deve quebrar a operação
        avisos = ("<br><span style='color:#d35400'>⚠️ " + "<br>".join(res.avisos) + "</span>") if res.avisos else ""
        self._resultado.setText(
            f"<span style='color:#27ae60'>✅ Mapa gerado.</span><br>"
            f"{len(res.arquivos_py)} arquivo(s) .py · {len(res.arquivos_outros)} outro(s) · "
            f"<b>{res.total_linhas}</b> linha(s) no total.<br>"
            f"<small>Salvo em: {res.caminho_saida}</small>{avisos}")

    def _ao_falhar(self, msg):
        self._botao.setEnabled(True)
        self._resultado.setText(f"<span style='color:#c0392b'>❌ Falha inesperada: {msg}</span>")

    def _copiar(self):
        if not self._conteudo_mapa:
            return
        try:
            clipboard.copiar(self._conteudo_mapa)
            self._botao_copiar.setText("Copiado ✓")
        except Exception as e:
            self._resultado.setText(
                self._resultado.text() +
                f"<br><span style='color:#c0392b'>❌ Não consegui copiar: {e}</span>")

    def atualizar(self):
        super().atualizar()
        # troca de aba/projeto: zera o estado do mapa (cada projeto tem o seu)
        if hasattr(self, "_botao_copiar"):
            self._conteudo_mapa = None
            self._botao_copiar.setEnabled(False)
            self._botao_copiar.setText("Copiar mapa")
            self._botao_copiar_aviso.setText("📋 Copiar aviso")
            self._resultado.setText("")
