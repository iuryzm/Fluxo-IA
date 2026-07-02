"""Página Histórico / Estatísticas: agrega e exibe o histórico do projeto corrente.

Não roda o core nem grava nada — só lê (estatisticas.calcular) e mostra. Recalcula
ao ficar visível (showEvent), para refletir comandos rodados na mesma sessão sem
precisar trocar de aba de projeto.
"""
import time
# QtCharts vem no PySide6-Addons. Import protegido: se faltar no ambiente, a página
# degrada para "gráfico indisponível" em vez de derrubar a janela inteira.
try:
    from PySide6.QtCharts import (
        QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis,
    )
    from PySide6.QtCore import QDateTime, QPointF
    from PySide6.QtGui import QPainter
    _CHARTS_OK = True
except ImportError:
    _CHARTS_OK = False

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QLabel, QTextEdit

from pyresumidor.gui.paginas.base import PaginaBase
from pyresumidor.core import estatisticas


_NOMES = {"mapear": "Mapear", "extrair": "Extrair", "aplicar": "Aplicar"}


class PaginaEstatisticas(PaginaBase):
    titulo = "Histórico / Estatísticas"
    descricao = "Resumo das execuções e evolução do projeto corrente."

    def __init__(self):
        super().__init__()
        layout = self.layout()
        idx = layout.indexOf(self._estado) + 1

        self._resumo = QLabel("")
        self._resumo.setWordWrap(True)
        self._resumo.setTextFormat(Qt.TextFormat.RichText)
        self._resumo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._botao_atualizar = QPushButton("Atualizar")
        self._botao_atualizar.clicked.connect(self._recalcular)

        self._lista = QTextEdit()
        self._lista.setReadOnly(True)
        self._lista.setMaximumHeight(160)

        layout.insertWidget(idx, self._resumo)
        layout.insertWidget(idx + 1, self._botao_atualizar)
        layout.insertWidget(idx + 2, self._lista)

        # Gráfico (só se QtCharts disponível). _grafico_msg cobre o caso degradado.
        self._chart_view = None
        if _CHARTS_OK:
            self._chart_view = QChartView()
            self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._chart_view.setMinimumHeight(260)
            layout.insertWidget(idx + 3, self._chart_view)
            self._grafico_msg = QLabel("")
            self._grafico_msg.setWordWrap(True)
            layout.insertWidget(idx + 4, self._grafico_msg)
        else:
            self._grafico_msg = QLabel(
                "<i>Gráfico indisponível (PySide6.QtCharts não encontrado). "
                "O resumo e o histórico acima continuam funcionando.</i>")
            self._grafico_msg.setWordWrap(True)
            self._grafico_msg.setTextFormat(Qt.TextFormat.RichText)
            layout.insertWidget(idx + 3, self._grafico_msg)

    def _recalcular(self):
        PaginaBase.atualizar(self)
        if self._projeto is None or not self._projeto.gitignore:
            self._resumo.setText(
                "<span style='color:#d35400'>⚠️ Defina um .gitignore válido em "
                "<b>Identificar Projeto</b> para ver as estatísticas.</span>")
            self._lista.clear()
            self._limpar_grafico()
            return

        s = estatisticas.calcular(self._projeto.gitignore)

        if s.total_execucoes == 0:
            self._resumo.setText("Nenhuma execução registrada ainda neste projeto.")
            self._lista.clear()
            self._limpar_grafico()
            return

        partes_cmd = []
        for chave in ("mapear", "extrair", "aplicar"):
            if chave in s.por_comando:
                partes_cmd.append(f"{_NOMES[chave]}: <b>{s.por_comando[chave]}</b>")
        linha_cmd = " · ".join(partes_cmd) if partes_cmd else "—"

        tamanho = ""
        if s.ultimo_mapa.get("total_linhas") is not None:
            tamanho = (f"<br>Tamanho atual (último mapa): "
                       f"<b>{s.ultimo_mapa['total_linhas']}</b> linha(s)")

        # Top-3 arquivos do último mapa (maiores) — responde "quais arquivos", não só o total.
        top_mapa = ""
        if s.ultimo_mapa_por_arquivo:
            maiores = sorted(s.ultimo_mapa_por_arquivo.items(),
                             key=lambda kv: kv[1], reverse=True)[:3]
            itens = " · ".join(f"{rel}: <b>{n}</b>" for rel, n in maiores)
            top_mapa = f"<br><small>Maiores arquivos: {itens}</small>"

        # Top-3 arquivos mais alterados no último aplicar (por add+rem).
        top_aplicar = ""
        if s.ultimo_aplicar_por_arquivo:
            mais = sorted(s.ultimo_aplicar_por_arquivo.items(),
                          key=lambda kv: (kv[1].get("add", 0) + kv[1].get("rem", 0)),
                          reverse=True)[:3]
            itens = " · ".join(
                f"{rel}: <span style='color:#1e7e34'>+{d.get('add', 0)}</span>/"
                f"<span style='color:#c0392b'>−{d.get('rem', 0)}</span>"
                for rel, d in mais)
            top_aplicar = f"<br><small>Último apply por arquivo: {itens}</small>"

        self._resumo.setText(
            f"<b>{s.total_execucoes}</b> execução(ões) · {linha_cmd}<br>"
            f"Linhas aplicadas: <span style='color:#1e7e34'>+{s.total_adicionadas}</span> / "
            f"<span style='color:#c0392b'>−{s.total_removidas}</span>{tamanho}{top_mapa}{top_aplicar}")

        from pyresumidor.core.armazenamento import listar_historico
        linhas = []
        for e in listar_historico(self._projeto.gitignore):
            ts = e.get("ts")
            quando = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"
            cmd = _NOMES.get(e.get("comando"), e.get("comando", "?"))
            resumo = e.get("resumo") or {}
            detalhe = self._detalhe(e.get("comando"), resumo)
            linhas.append(f"{quando} · {cmd}{detalhe}")
        self._lista.setPlainText("\n".join(linhas))

        self._desenhar_grafico(s)

    def _limpar_grafico(self):
        if self._chart_view is not None:
            self._chart_view.setChart(QChart())
        if hasattr(self, "_grafico_msg"):
            self._grafico_msg.setText("")

    def _desenhar_grafico(self, s):
        if not _CHARTS_OK or self._chart_view is None:
            return
        # Precisa de pelo menos 2 mapeamentos para uma curva de evolução fazer sentido.
        if len(s.evolucao_linhas) < 2:
            self._chart_view.setChart(QChart())
            self._grafico_msg.setText(
                "<i>Registre ao menos 2 mapeamentos para ver a evolução no gráfico.</i>")
            return
        self._grafico_msg.setText("")

        chart = QChart()
        chart.setTitle("Evolução do projeto (por mapeamento)")

        serie_linhas = QLineSeries()
        serie_linhas.setName("Linhas")
        for ts, val in s.evolucao_linhas:
            serie_linhas.append(float(ts) * 1000.0, float(val))  # QDateTime usa ms

        serie_arq = QLineSeries()
        serie_arq.setName("Arquivos")
        for ts, val in s.evolucao_arquivos:
            serie_arq.append(float(ts) * 1000.0, float(val))

        chart.addSeries(serie_linhas)
        chart.addSeries(serie_arq)

        eixo_x = QDateTimeAxis()
        eixo_x.setFormat("dd/MM HH:mm")
        eixo_x.setTitleText("Mapeamento")
        chart.addAxis(eixo_x, Qt.AlignmentFlag.AlignBottom)
        serie_linhas.attachAxis(eixo_x)
        serie_arq.attachAxis(eixo_x)

        eixo_y_linhas = QValueAxis()
        eixo_y_linhas.setTitleText("Linhas")
        eixo_y_linhas.setLabelFormat("%d")
        chart.addAxis(eixo_y_linhas, Qt.AlignmentFlag.AlignLeft)
        serie_linhas.attachAxis(eixo_y_linhas)

        eixo_y_arq = QValueAxis()
        eixo_y_arq.setTitleText("Arquivos")
        eixo_y_arq.setLabelFormat("%d")
        chart.addAxis(eixo_y_arq, Qt.AlignmentFlag.AlignRight)
        serie_arq.attachAxis(eixo_y_arq)

        self._chart_view.setChart(chart)

    def _detalhe(self, comando, resumo):
        if comando == "mapear":
            return f" · {resumo.get('total_linhas', '?')} linhas"
        if comando == "extrair":
            return f" · {resumo.get('encontrados', '?')}/{resumo.get('itens', '?')} itens"
        if comando == "aplicar":
            return (f" · {resumo.get('gravados', '?')} arq · "
                    f"+{resumo.get('adicionadas', 0)}/−{resumo.get('removidas', 0)}")
        return ""

    def atualizar(self):
        super().atualizar()
        if hasattr(self, "_resumo"):
            self._recalcular()

    def showEvent(self, evento):
        super().showEvent(evento)
        if hasattr(self, "_resumo"):
            self._recalcular()
