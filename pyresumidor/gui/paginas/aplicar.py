"""Página Aplicar: simula e aplica o plano de operações da IA.

Única página que ESCREVE nos arquivos do projeto. Por isso: (1) 'Aplicar de
verdade' só habilita após uma simulação bem-sucedida; (2) editar o campo
re-desabilita, forçando nova simulação (você nunca grava um texto diferente do
que revisou); (3) confirmação lista os arquivos antes de gravar; (4) backups .bak
são criados por padrão. O diff aparece inline, colorido.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QPushButton, QLabel, QTextEdit, QHBoxLayout, QMessageBox,
)

from pyresumidor.gui.paginas.base import PaginaBase
from pyresumidor.gui.workers import rodar_em_thread
from pyresumidor.core import (
    aplicador,
    executor_sequencia,
)
from pyresumidor.core import clipboard
from pyresumidor.core.armazenamento import caminho_entrada_aplicar
from pyresumidor.core.armazenamento import caminho_entrada_aplicar, registrar_historico


class PaginaAplicar(PaginaBase):
    titulo = "Aplicar"
    descricao = ("Cole o PLANO (JSON) num campo e o CÓDIGO (blocos # --- id=... ---) "
                 "no outro — sem crases. Simule primeiro; só então o aplicar é liberado.")

    _COR_ADD = "#1e7e34"
    _COR_DEL = "#c0392b"
    _COR_HUNK = "#2980b9"
    _COR_CTX = "#555555"

    def __init__(self):
        super().__init__()
        layout = self.layout()
        idx = layout.indexOf(self._estado) + 1
        self._botao_ajuda = QPushButton("?")
        self._botao_ajuda.setFixedWidth(28)
        self._botao_ajuda.setToolTip("Ver um exemplo de plano + blocos de código.")
        self._botao_ajuda.clicked.connect(self._mostrar_exemplo)
        _linha_ajuda = QHBoxLayout()
        _linha_ajuda.addStretch()
        _linha_ajuda.addWidget(self._botao_ajuda)
        layout.insertLayout(idx, _linha_ajuda)
        idx += 1

        self._campo_plano = QTextEdit()
        self._campo_plano.setPlaceholderText('Plano (JSON): {"operacoes": [...]} — sem crases')
        self._campo_plano.setAcceptRichText(False)
        self._campo_plano.setFont(QFont("Consolas", 9))
        self._campo_plano.textChanged.connect(self._on_campo_mudou)

        self._botao_colar_plano = QPushButton("Colar plano")
        self._botao_colar_plano.clicked.connect(self._colar_plano)

        self._campo_codigo = QTextEdit()
        self._campo_codigo.setPlaceholderText("Código: blocos # --- id=<id> --- — sem crases")
        self._campo_codigo.setAcceptRichText(False)
        self._campo_codigo.setFont(QFont("Consolas", 9))
        self._campo_codigo.textChanged.connect(self._on_campo_mudou)

        self._botao_colar_codigo = QPushButton("Colar código")
        self._botao_colar_codigo.clicked.connect(self._colar_codigo)

        linha_acoes = QHBoxLayout()
        self._botao_simular = QPushButton("Simular (dry-run)")
        self._botao_simular.clicked.connect(self._simular)
        self._botao_aplicar = QPushButton("Aplicar de verdade")
        self._botao_aplicar.setEnabled(False)
        self._botao_aplicar.clicked.connect(self._aplicar)
        linha_acoes.addWidget(self._botao_simular)
        linha_acoes.addWidget(self._botao_aplicar)

        # Botão do modo sequenciado (modo C): só habilita quando a simulação prepara
        # um plano com comando(s). Dispara o diálogo de lote + execução (5e-ii).
        self._botao_executar_seq = QPushButton("Executar sequência (roda comandos)")
        self._botao_executar_seq.setEnabled(False)
        self._botao_executar_seq.setVisible(False)
        self._botao_executar_seq.clicked.connect(self._executar_sequencia)

        self._resultado = QLabel("")
        self._resultado.setWordWrap(True)
        self._resultado.setTextFormat(Qt.TextFormat.RichText)
        # Permite selecionar e copiar o texto de avisos/erros com o mouse.
        self._resultado.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._diff = QTextEdit()
        self._diff.setReadOnly(True)
        self._diff.setFont(QFont("Consolas", 9))
        self._diff.setVisible(False)

        # Área de saída dos comandos (modo sequenciado): stdout/stderr/exit, copiável.
        self._saida_cmd = QTextEdit()
        self._saida_cmd.setReadOnly(True)
        self._saida_cmd.setFont(QFont("Consolas", 9))
        self._saida_cmd.setVisible(False)

        layout.insertWidget(idx, QLabel("<b>Plano (JSON)</b>"))
        layout.insertWidget(idx + 1, self._campo_plano)
        layout.insertWidget(idx + 2, self._botao_colar_plano)
        layout.insertWidget(idx + 3, QLabel("<b>Código (blocos)</b>"))
        layout.insertWidget(idx + 4, self._campo_codigo)
        layout.insertWidget(idx + 5, self._botao_colar_codigo)
        layout.insertLayout(idx + 6, linha_acoes)
        layout.insertWidget(idx + 7, self._botao_executar_seq)
        layout.insertWidget(idx + 8, self._resultado)
        layout.insertWidget(idx + 9, self._diff)
        layout.insertWidget(idx + 10, self._saida_cmd)

        self._texto_simulado = None
        self._ultimo_res = None
        self._modo_aplicar = False   # guarda o modo do disparo atual (sem lambda no sinal)

        self._botao_limpar = QPushButton("Limpar campos")
        self._botao_limpar.clicked.connect(self._limpar)
        layout.insertWidget(idx + 11, self._botao_limpar)

    def _montar_texto(self):
        plano = self._campo_plano.toPlainText().strip()
        codigo = self._campo_codigo.toPlainText().strip()
        cb4 = chr(96) * 4
        cb3 = chr(96) * 3
        partes = []
        if plano:
            partes.append(f"{cb4}json\n{plano}\n{cb4}")
        if codigo:
            partes.append(f"{cb3}python\n{codigo}\n{cb3}")
        return "\n\n".join(partes)

    def _on_campo_mudou(self):
        if self._texto_simulado is not None and self._montar_texto() != self._texto_simulado:
            self._botao_aplicar.setEnabled(False)

    def _colar_plano(self):
        try:
            texto = clipboard.colar()
        except Exception as e:
            self._resultado.setText(f"<span style='color:#c0392b'>❌ Não consegui colar: {e}</span>")
            return
        # se o texto tiver cercas/json, extrai só o JSON; senão usa como veio
        import re
        m = re.search(r'`{3,}json\s*(.*?)\s*`{3,}', texto, re.DOTALL | re.IGNORECASE)
        if m:
            self._campo_plano.setPlainText(m.group(1).strip())
        else:
            ini, fim = texto.find('{'), texto.rfind('}')
            if ini != -1 and fim != -1:
                self._campo_plano.setPlainText(texto[ini:fim + 1].strip())
            else:
                self._campo_plano.setPlainText(texto.strip())

    def _colar_codigo(self):
        try:
            texto = clipboard.colar()
        except Exception as e:
            self._resultado.setText(f"<span style='color:#c0392b'>❌ Não consegui colar: {e}</span>")
            return
        import re
        mc = re.search(r'^#\s*---\s*id=', texto, re.MULTILINE)
        if mc:
            trecho = texto[mc.start():]
            trecho = re.sub(r'^`{3,}.*$', '', trecho, flags=re.MULTILINE)
            self._campo_codigo.setPlainText(trecho.strip())
        else:
            self._campo_codigo.setPlainText(texto.strip())

    def _validar_entrada(self):
        if self._projeto is None or not self._projeto.gitignore:
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ Defina um .gitignore válido na aba "
                "<b>Identificar Projeto</b> antes de aplicar.</span>")
            return None
        if not self._campo_plano.toPlainText().strip():
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ Cole o plano JSON no primeiro campo.</span>")
            return None
        texto = self._montar_texto()
        entrada = caminho_entrada_aplicar(self._projeto.gitignore)
        try:
            entrada.write_text(texto, encoding="utf-8")
        except Exception as e:
            self._resultado.setText(f"<span style='color:#c0392b'>❌ Não consegui gravar a entrada: {e}</span>")
            return None
        return texto, entrada

    def _simular(self):
        dados = self._validar_entrada()
        if dados is None:
            return
        texto, entrada = dados
        self._texto_simulado = texto
        self._modo_aplicar = False
        self._botao_simular.setEnabled(False)
        self._botao_aplicar.setEnabled(False)
        self._resultado.setText("⏳ Simulando…")
        self._diff.setVisible(False)
        rodar_em_thread(
            self, aplicador.executar,
            self._ao_concluir, self._ao_falhar,
            str(entrada), self._projeto.raiz, False, None, False,
        )

    def _aplicar(self):
        if self._texto_simulado is None:
            self._resultado.setText("<span style='color:#d35400'>⚠️ Simule primeiro.</span>")
            return
        if self._montar_texto() != self._texto_simulado:
            self._resultado.setText(
                "<span style='color:#d35400'>⚠️ O texto mudou desde a simulação. Simule de novo.</span>")
            return
        if self._ultimo_res is None:
            return
        alterados = [a.caminho for a in self._ultimo_res.arquivos if a.diff]
        if not alterados:
            self._resultado.setText("<span style='color:#d35400'>⚠️ Nada para aplicar.</span>")
            return
        lista = "\n".join(f"  • {c}" for c in alterados)
        cx = QMessageBox(self)
        cx.setWindowTitle("Confirmar aplicação")
        cx.setIcon(QMessageBox.Icon.Warning)
        cx.setText(f"Gravar alterações em {len(alterados)} arquivo(s)?\n\n{lista}\n\n"
                   "Backups .bak serão criados para os arquivos existentes.")
        cx.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        cx.setDefaultButton(QMessageBox.StandardButton.No)
        if cx.exec() != QMessageBox.StandardButton.Yes:
            return
        entrada = caminho_entrada_aplicar(self._projeto.gitignore)
        entrada.write_text(self._texto_simulado, encoding="utf-8")
        self._modo_aplicar = True
        self._botao_simular.setEnabled(False)
        self._botao_aplicar.setEnabled(False)
        self._resultado.setText("⏳ Aplicando…")
        rodar_em_thread(
            self, aplicador.executar,
            self._ao_concluir, self._ao_falhar,
            str(entrada), self._projeto.raiz, True, None, False,
        )

    def _ao_concluir(self, res):
        # roda na thread de UI: o sinal vai para este método (slot do QObject página),
        # não para um lambda. Por isso tocar widgets aqui é seguro.
        aplicado = self._modo_aplicar
        self._botao_simular.setEnabled(True)
        self._ultimo_res = res

        if not res.sucesso:
            erros = "<br>".join(res.erros) or "erro desconhecido"
            self._resultado.setText(f"<span style='color:#c0392b'>❌ {erros}</span>")
            self._diff.setVisible(False)
            return

        # Modo sequenciado (modo C): o core preparou passos + estados; NÃO gravou nada.
        # Exibimos a sequência e deixamos a execução para o botão dedicado (5e-ii).
        if res.sequenciado:
            self._exibir_sequencia_preparada(res)
            return

        erros_arq = []
        for a in res.arquivos:
            for e in a.erros:
                erros_arq.append(f"{a.caminho}: {e}")

        self._render_diff(res.arquivos)

        avisos = ("<br><span style='color:#d35400'>⚠️ " + "<br>".join(res.avisos) + "</span>") if res.avisos else ""
        bloco_erros = ("<br><span style='color:#c0392b'>⚠️ Erros por arquivo:<br>" +
                       "<br>".join(erros_arq) + "</span>") if erros_arq else ""

        if aplicado:
            gravados = [a for a in res.arquivos if a.gravado]
            backups = [a.caminho for a in gravados if a.backup_criado]
            bk = f"<br><small>Backups .bak: {', '.join(backups)}</small>" if backups else ""
            self._resultado.setText(
                f"<span style='color:#1e7e34'>✅ Aplicado.</span> "
                f"{len(gravados)} arquivo(s) gravado(s) · "
                f"<span style='color:#1e7e34'>+{res.total_adicionadas}</span> / "
                f"<span style='color:#c0392b'>−{res.total_removidas}</span>{bk}{bloco_erros}{avisos}")
            self._botao_aplicar.setEnabled(False)
            self._texto_simulado = None
            try:
                registrar_historico(
                    self._projeto.gitignore, "aplicar", True,
                    res.resumo_historico(len(gravados)))
            except Exception:
                pass
        else:
            mudou = any(a.diff for a in res.arquivos)
            if mudou:
                self._botao_aplicar.setEnabled(True)
                self._resultado.setText(
                    f"<span style='color:#2980b9'>👀 Simulação (nada gravado).</span> "
                    f"<span style='color:#1e7e34'>+{res.total_adicionadas}</span> / "
                    f"<span style='color:#c0392b'>−{res.total_removidas}</span>. "
                    f"Revise o diff e clique <b>Aplicar de verdade</b>.{bloco_erros}{avisos}")
            else:
                self._resultado.setText(
                    f"<span style='color:#d35400'>➖ Nenhuma mudança gerada pelo plano.</span>{bloco_erros}{avisos}")

    def _render_diff(self, arquivos):
        self._diff.clear()
        cursor = self._diff.textCursor()

        def cor(hex_str):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(hex_str))
            return fmt

        houve = False
        for a in arquivos:
            if not a.diff:
                continue
            houve = True
            for linha in a.diff.splitlines():
                if linha.startswith("+") and not linha.startswith("+++"):
                    fmt = cor(self._COR_ADD)
                elif linha.startswith("-") and not linha.startswith("---"):
                    fmt = cor(self._COR_DEL)
                elif linha.startswith("@@"):
                    fmt = cor(self._COR_HUNK)
                else:
                    fmt = cor(self._COR_CTX)
                cursor.insertText(linha + "\n", fmt)
        self._diff.setVisible(houve)

    def _ao_falhar(self, msg):
        self._botao_simular.setEnabled(True)
        self._resultado.setText(f"<span style='color:#c0392b'>❌ Falha inesperada: {msg}</span>")

    def atualizar(self):
        super().atualizar()
        if hasattr(self, "_botao_aplicar"):
            self._texto_simulado = None
            self._ultimo_res = None
            self._modo_aplicar = False
            self._botao_aplicar.setEnabled(False)
            self._botao_aplicar.setVisible(True)
            self._botao_executar_seq.setVisible(False)
            self._botao_executar_seq.setEnabled(False)
            self._saida_cmd.setVisible(False)
            self._resultado.setText("")
            self._diff.setVisible(False)
            self._campo_plano.clear()
            self._campo_codigo.clear()

    def _limpar(self):
        self._campo_plano.clear()
        self._campo_codigo.clear()
        self._resultado.setText("")
        self._diff.setVisible(False)
        self._texto_simulado = None
        self._ultimo_res = None
        self._botao_aplicar.setEnabled(False)
        self._botao_aplicar.setVisible(True)
        self._botao_executar_seq.setVisible(False)
        self._botao_executar_seq.setEnabled(False)
        self._saida_cmd.setVisible(False)

    def _exibir_sequencia_preparada(self, res):
        """Modo sequenciado (5e-i): mostra a sequência que o core preparou, SEM executar.

        Lista os passos na ordem do plano — edições (com +/−) e comandos (com gates) —
        e habilita o botão 'Executar sequência'. Nada roda aqui; a execução é ato
        deliberado do botão (5e-ii), que abre o diálogo de lote antes de rodar.
        """
        self._render_diff(res.arquivos)  # os diffs das edições aparecem inline como sempre

        linhas = ["<b>Sequência preparada</b> (nada executado ainda):"]
        n_cmd = 0
        for passo in res.passos:
            if passo.tipo == "edicao":
                arq = next((a for a in res.arquivos if a.caminho == passo.caminho), None)
                mais = f" <span style='color:#1e7e34'>+{arq.adicionadas}</span>/<span style='color:#c0392b'>−{arq.removidas}</span>" if arq else ""
                linhas.append(f"[{passo.ordem}] 📝 edição: {passo.caminho}{mais}")
            else:
                pc = passo.comando
                n_cmd += 1
                gates = []
                if pc.espera_exit is not None:
                    gates.append(f"exit=={pc.espera_exit}")
                if pc.espera_conter is not None:
                    gates.append(f"contém {pc.espera_conter!r}")
                g = f" <small>(gate: {', '.join(gates)})</small>" if gates else ""
                desc = f" — {pc.descricao}" if pc.descricao else ""
                linhas.append(f"[{passo.ordem}] ▶ <b>comando</b>: <code>{pc.comando}</code>{desc}{g}")

        self._resultado.setText(
            "<span style='color:#8e44ad'>🔗 Modo sequenciado.</span> "
            f"{n_cmd} comando(s) a executar na sua máquina.<br>" + "<br>".join(linhas) +
            "<br><br><span style='color:#d35400'>Revise acima. Clique <b>Executar sequência</b> "
            "para autorizar e rodar os comandos.</span>")

        self._botao_executar_seq.setVisible(True)
        self._botao_executar_seq.setEnabled(True)
        self._botao_aplicar.setVisible(False)   # no modo C não há 'aplicar' separado
        self._saida_cmd.setVisible(False)

    def _executar_sequencia(self):
        """Slot do botão 'Executar sequência' (modo C): diálogo de lote (opt-in) e,
        se confirmado, dispara o worker que grava as edições e roda os comandos.

        O diálogo é o ÚNICO ponto de decisão humana: lista todos os comandos, o
        AMBIENTE em que vão rodar (venv do projeto-alvo, se houver, ou sistema) e o
        aviso de que rodam na máquina. Confirmar = autorizar o lote; o confirmador
        passado ao executor é sempre-sim (a decisão já foi tomada aqui). Cancelar =
        nada roda.
        """
        if self._ultimo_res is None or not self._ultimo_res.sequenciado:
            return
        comandos = [p.comando for p in self._ultimo_res.passos if p.tipo == "comando"]
        if not comandos:
            return

        _env, rotulo_ambiente = executor_sequencia.montar_ambiente(self._projeto.raiz)

        linhas = []
        for i, pc in enumerate(comandos):
            desc = f"\n     {pc.descricao}" if pc.descricao else ""
            linhas.append(f"  [{i}] {pc.comando}{desc}")
        corpo = "\n".join(linhas)

        cx = QMessageBox(self)
        cx.setWindowTitle("Autorizar execução de comandos")
        cx.setIcon(QMessageBox.Icon.Warning)
        cx.setText(
            f"Este plano executará {len(comandos)} comando(s) na SUA máquina, via PowerShell:\n\n"
            f"{corpo}\n\n"
            f"Ambiente de execução: {rotulo_ambiente}\n\n"
            "Os comandos rodam com as suas permissões. Edições serão gravadas (com .bak) "
            "na ordem do plano; se um comando com gate divergir, a sequência para.\n\n"
            "Autorizar a execução de TODOS os comandos acima?")
        cx.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        cx.setDefaultButton(QMessageBox.StandardButton.No)
        if cx.exec() != QMessageBox.StandardButton.Yes:
            self._resultado.setText("<span style='color:#d35400'>Execução cancelada. Nada foi rodado.</span>")
            return

        self._botao_executar_seq.setEnabled(False)
        self._botao_simular.setEnabled(False)
        self._resultado.setText("⏳ Executando a sequência…")
        # confirmador sempre-sim: a decisão de lote já foi tomada no diálogo acima.
        rodar_em_thread(
            self, executor_sequencia.executar_sequencia_empacotado,
            self._ao_concluir_seq, self._ao_falhar_seq,
            self._ultimo_res, self._projeto.raiz, (lambda pc: True),
        )

    def _ao_concluir_seq(self, empacotado):
        """Conclusão do worker de execução sequenciada (method slot, thread de UI).

        Renderiza cada comando (stdout/stderr/exit) na área copiável, o relatório de
        parada, e registra o histórico dos arquivos efetivamente gravados. O botão de
        execução fica desabilitado depois (rodar de novo exige re-simular).

        Contagem de gravados: só conta a edição que REALMENTE rodou — isto é, cujo passo
        veio ANTES do ponto de parada. Se a sequência parou num gate no passo N, as
        edições em N ou depois não foram gravadas (o executor não chegou a elas).
        """
        res = empacotado.res
        parou_em = empacotado.parou_em
        self._botao_simular.setEnabled(True)

        partes = []
        gravados = []
        for passo in res.passos:
            if passo.tipo == "edicao":
                if parou_em is None or passo.ordem < parou_em:
                    gravados.append(passo.caminho)
                    partes.append(f"📝 [{passo.ordem}] gravado: {passo.caminho}")
                else:
                    partes.append(f"📝 [{passo.ordem}] {passo.caminho} — NÃO gravado (sequência parou antes)")
                continue
            pc = passo.comando
            rc = passo.resultado_comando
            if not rc.executado:
                partes.append(f"▶ [{passo.ordem}] {pc.comando}\n   ⏭️ {rc.motivo_divergencia or 'não executado'}")
                continue
            ec = "timeout" if rc.expirou else f"exit {rc.exit_code}"
            estado = "DIVERGIU" if rc.divergiu else "ok"
            corpo = (rc.stdout + rc.stderr).rstrip()
            bloco = f"▶ [{passo.ordem}] {pc.comando}  ({ec}, {estado})"
            if corpo:
                bloco += "\n" + "\n".join(f"   {ln}" for ln in corpo.splitlines())
            if rc.divergiu:
                bloco += f"\n   ⛔ {rc.motivo_divergencia}"
            partes.append(bloco)

        self._saida_cmd.setPlainText("\n\n".join(partes))
        self._saida_cmd.setVisible(True)

        if parou_em is not None:
            self._resultado.setText(
                f"<span style='color:#c0392b'>⛔ Sequência interrompida no passo {parou_em}.</span> "
                f"Passos seguintes não executados. "
                f"<span style='color:#1e7e34'>{len(gravados)} arquivo(s) gravado(s).</span>")
        else:
            self._resultado.setText(
                f"<span style='color:#1e7e34'>✅ Sequência concluída.</span> "
                f"{len(gravados)} arquivo(s) gravado(s).")

        try:
            registrar_historico(
                self._projeto.gitignore, "aplicar", parou_em is None,
                res.resumo_historico(len(gravados)))
        except Exception:
            pass

        self._botao_executar_seq.setEnabled(False)   # execução é única; re-simule para rodar de novo
        self._texto_simulado = None

    def _ao_falhar_seq(self, msg):
        """Falha inesperada no worker de execução sequenciada (method slot)."""
        self._botao_simular.setEnabled(True)
        self._botao_executar_seq.setEnabled(True)
        self._resultado.setText(
            f"<span style='color:#c0392b'>❌ Falha ao executar a sequência: {msg}</span>")

    def _mostrar_exemplo(self):
        """Mostra um exemplo de plano + blocos aceitos nesta página.

        NOTA DE MANUTENÇÃO: mantenha este exemplo em sincronia com as regras do
        INSTRUCOES_IA do aplicador (pyresumidor/core/aplicador.py). Se um formato de
        ação mudar lá, atualize aqui — um exemplo desatualizado ensina o errado.
        """
        exemplo = (
            "Cole o PLANO no campo de plano e os BLOCOS DE CÓDIGO no campo de código.\n\n"
            "PLANO (JSON):\n"
            "{\n"
            '  "operacoes": [\n'
            '    {"acao": "substituir", "arquivo": "x.py", "tipo": "funcao", "alvo": "minha_funcao", "codigo_id": "b1"},\n'
            '    {"acao": "trecho", "arquivo": "x.py", "tipo": "funcao", "alvo": "outra", "posicao": "depois", "ancora_id": "a1", "codigo_id": "b2"},\n'
            '    {"acao": "adicionar", "arquivo": "x.py", "tipo": "metodo", "alvo": "Classe.novo_metodo", "codigo_id": "b3"},\n'
            '    {"acao": "adicionar_import", "arquivo": "x.py", "modulo": "os.path", "nomes": ["join"]},\n'
            '    {"acao": "comando", "comando": "pytest -q", "descricao": "roda os testes", "espera_exit": 0}\n'
            "  ]\n"
            "}\n\n"
            "BLOCOS DE CÓDIGO (campo separado):\n"
            "# --- id=b1 ---\n"
            "def minha_funcao():\n"
            "    return 42\n"
            "# --- id=a1 ---\n"
            "    linha_ancora_existente_copiada_do_codigo\n"
            "# --- id=b2 ---\n"
            "    codigo_novo_a_inserir\n\n"
            "Ações:\n"
            "• substituir — troca um nó (funcao/classe/metodo) inteiro pelo codigo_id.\n"
            "• trecho — insere/substitui relativo a uma âncora (copie a âncora do CÓDIGO\n"
            "  extraído, byte a byte, nunca do mapa).\n"
            "• adicionar — cria um nó novo (funcao/classe/metodo) que ainda não existe.\n"
            "• adicionar_import — acrescenta nomes a um import, sem âncora.\n"
            "• comando — executa PowerShell (só roda com sua autorização; pode ter gates\n"
            "  espera_exit/espera_conter que param a sequência se divergir)."
        )
        self._mostrar_ajuda("Exemplo — plano de aplicação", exemplo)
