"""Página Extrair: recebe a resposta JSON da IA e extrai os trechos pedidos.

A resposta colada é gravada como arquivo de entrada em dados/ (entrada do comando,
para o histórico da Fase 4) e passada a executar_extracao no worker. O worker lê
SEMPRE do campo visível — não do clipboard às cegas; o botão 'colar' é só uma
conveniência que preenche o campo.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QTextEdit,
    QCheckBox,
    QHBoxLayout,
)

from pyresumidor.gui.paginas.base import PaginaBase
from pyresumidor.gui.workers import rodar_em_thread
from pyresumidor.core import extrator
from pyresumidor.core import clipboard
from pyresumidor.core.armazenamento import caminho_entrada_extrair, caminho_saida_extrair
from pyresumidor.core.armazenamento import (
    caminho_entrada_extrair, caminho_saida_extrair, registrar_historico)


class PaginaExtrair(PaginaBase):
    titulo = "Extrair"
    descricao = ("Cole aqui a resposta da IA (o JSON com arquivos/classes/funções "
                 "pedidos). O resultado sai pronto para colar de volta no chat.")

    def __init__(self):
        super().__init__()
        layout = self.layout()
        idx = layout.indexOf(self._estado) + 1
        self._botao_ajuda = QPushButton("?")
        self._botao_ajuda.setFixedWidth(28)
        self._botao_ajuda.setToolTip("Ver um exemplo do JSON de extração.")
        self._botao_ajuda.clicked.connect(self._mostrar_exemplo)
        _linha_ajuda = QHBoxLayout()
        _linha_ajuda.addStretch()
        _linha_ajuda.addWidget(self._botao_ajuda)
        layout.insertLayout(idx, _linha_ajuda)
        idx += 1

        self._campo = QTextEdit()
        self._campo.setPlaceholderText("Cole aqui a resposta da IA (JSON)…")
        self._campo.setAcceptRichText(False)

        self._botao_colar = QPushButton("Colar da área de transferência")
        self._botao_colar.clicked.connect(self._colar_entrada)

        self._chk_instrucoes = QCheckBox("Anexar instruções do aplicador à saída")
        self._chk_instrucoes.setChecked(True)
        self._chk_instrucoes.setToolTip(
            "Quando marcado, o guia de formato para a IA é anexado ao fim do "
            "resultado (equivale a NÃO usar --sem-instrucoes na CLI).")

        self._botao = QPushButton("Extrair")
        self._botao.clicked.connect(self._extrair)

        self._botao_copiar = QPushButton("Copiar resultado")
        self._botao_copiar.setEnabled(False)
        self._botao_copiar.clicked.connect(self._copiar)

        self._resultado = QLabel("")
        self._resultado.setWordWrap(True)
        self._resultado.setTextFormat(Qt.TextFormat.RichText)
        # Permite selecionar e copiar o texto de avisos/erros com o mouse (além do
        # botão dedicado abaixo).
        self._resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._botao_copiar_aviso = QPushButton("📋 Copiar aviso")
        self._botao_copiar_aviso.clicked.connect(self._copiar_aviso)

        layout.insertWidget(idx, self._campo)
        layout.insertWidget(idx + 1, self._botao_colar)
        layout.insertWidget(idx + 2, self._chk_instrucoes)
        layout.insertWidget(idx + 3, self._botao)
        layout.insertWidget(idx + 4, self._botao_copiar)
        layout.insertWidget(idx + 5, self._resultado)
        layout.insertWidget(idx + 6, self._botao_copiar_aviso)

        self._conteudo_saida = None

        self._botao_limpar = QPushButton("Limpar campos")
        self._botao_limpar.clicked.connect(self._limpar)
        layout.insertWidget(idx + 7, self._botao_limpar)

    def _colar_entrada(self):
        try:
            texto = clipboard.colar()
        except Exception as e:
            self._resultado.setText(f"<span style='color:#c0392b'>❌ Não consegui colar: {e}</span>")
            return
        self._campo.setPlainText(texto)

    def _extrair(self):
        if self._projeto is None or not self._projeto.gitignore:
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ Defina um .gitignore válido na aba "
                "<b>Identificar Projeto</b> antes de extrair.</span>")
            return
        texto = self._campo.toPlainText().strip()
        if not texto:
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ Cole a resposta da IA no campo acima "
                "(ou use o botão de colar).</span>")
            return

        entrada = caminho_entrada_extrair(self._projeto.gitignore)
        try:
            entrada.write_text(texto, encoding="utf-8")
        except Exception as e:
            self._resultado.setText(f"<span style='color:#c0392b'>❌ Não consegui gravar a entrada: {e}</span>")
            return

        saida = caminho_saida_extrair(self._projeto.gitignore)
        self._botao.setEnabled(False)
        self._botao_copiar.setEnabled(False)
        self._resultado.setText("⏳ Extraindo…")

        rodar_em_thread(
            self,
            extrator.executar_extracao,
            self._ao_concluir,
            self._ao_falhar,
            str(entrada),                              # resposta_path_str
            self._projeto.raiz,                        # projeto_path_str
            str(saida),                                # saida_path_str
            incluir_instrucoes=self._chk_instrucoes.isChecked(),
        )

    def _ao_concluir(self, res):
        self._botao.setEnabled(True)
        if not res.sucesso:
            erros = "<br>".join(res.erros) or "erro desconhecido"
            self._resultado.setText(f"<span style='color:#c0392b'>❌ {erros}</span>")
            return

        self._conteudo_saida = res.conteudo
        self._botao_copiar.setEnabled(True)
        achados = sum(1 for i in res.itens if i.encontrado)
        total = len(res.itens)
        try:
            registrar_historico(
                self._projeto.gitignore, "extrair", True,
                {"itens": total, "encontrados": achados})
        except Exception:
            pass
        instr = "<br>(instruções do aplicador anexadas)" if res.instrucoes_anexadas else ""
        avisos = ("<br><span style='color:#d35400'>⚠️ " + "<br>".join(res.avisos) + "</span>") if res.avisos else ""
        self._resultado.setText(
            f"<span style='color:#27ae60'>✅ Extração concluída.</span><br>"
            f"<b>{achados}/{total}</b> item(ns) confirmado(s) como localizado(s)."
            f"<br><b>{res.total_linhas_extraidas}</b> linha(s) · "
            f"~<b>{res.tokens_estimados}</b> token(s) estimado(s) irão para o clipboard.<br>"
            f"<small>Salvo em: {res.caminho_saida}</small>{instr}{avisos}")

    def _ao_falhar(self, msg):
        self._botao.setEnabled(True)
        self._resultado.setText(f"<span style='color:#c0392b'>❌ Falha inesperada: {msg}</span>")

    def _copiar(self):
        if not self._conteudo_saida:
            return
        try:
            clipboard.copiar(self._conteudo_saida)
            self._botao_copiar.setText("Copiado ✓")
        except Exception as e:
            self._resultado.setText(
                self._resultado.text() +
                f"<br><span style='color:#c0392b'>❌ Não consegui copiar: {e}</span>")

    def atualizar(self):
        super().atualizar()
        if hasattr(self, "_botao_copiar"):
            self._conteudo_saida = None
            self._botao_copiar.setEnabled(False)
            self._botao_copiar.setText("Copiar resultado")
            self._botao_copiar_aviso.setText("📋 Copiar aviso")
            self._resultado.setText("")
            self._campo.clear()

    def _limpar(self):
        self._campo.clear()
        self._resultado.setText("")
        self._conteudo_saida = None
        self._botao_copiar.setEnabled(False)
        self._botao_copiar.setText("Copiar resultado")
        self._botao_copiar_aviso.setText("📋 Copiar aviso")

    def _mostrar_exemplo(self):
        """Mostra um exemplo do JSON de extração aceito nesta página.

        NOTA DE MANUTENÇÃO: mantenha este exemplo em sincronia com as regras do
        `instrucoes_ia` do mapear (pyresumidor/core/mapear.py). Se um formato de
        extração mudar lá, atualize aqui — um exemplo desatualizado ensina o errado.
        """
        exemplo = (
            "Cole no campo acima um JSON como este (peça à IA que o gere a partir do mapa):\n\n"
            "{\n"
            '  "arquivos_completos": [\n'
            '    "caminho/relativo/config.yaml"\n'
            "  ],\n"
            '  "classes": {\n'
            '    "pacote/modulo.py": ["NomeDaClasse"]\n'
            "  },\n"
            '  "funcoes": {\n'
            '    "pacote/modulo.py": ["nome_funcao", "NomeDaClasse.nome_metodo"]\n'
            "  },\n"
            '  "trechos": [\n'
            '    {"arquivo": "pacote/modulo.py", "alvo": "NomeDaClasse.metodo", "fatia": "primeiras:5"},\n'
            '    {"arquivo": "pacote/modulo.py", "fatia": "primeiras:15"}\n'
            "  ],\n"
            '  "sem_instrucoes": false\n'
            "}\n\n"
            "Dicas:\n"
            "• arquivos_completos: o arquivo inteiro (use com parcimônia; gasta contexto).\n"
            "• classes / funcoes: só os nós que precisa. Método = \"Classe.metodo\".\n"
            "• trechos: primeiras/últimas N linhas de um alvo (ou do arquivo, sem \"alvo\") —\n"
            "  para VER imports/assinaturas sem pagar o arquivo todo. É recorte, não âncora.\n"
            "• sem_instrucoes: true omite as instruções do aplicador (economiza tokens em\n"
            "  tarefas só de leitura)."
        )
        self._mostrar_ajuda("Exemplo — JSON de extração", exemplo)
