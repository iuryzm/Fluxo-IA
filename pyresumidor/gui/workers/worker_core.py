"""Worker genérico: roda uma função do core fora da thread de UI.

Genérico de propósito — recebe qualquer callable + args e emite o que ele
retornar. Mapear, Extrair e Aplicar reusam o mesmo worker. O sinal 'concluiu'
carrega o objeto Resultado* INTEIRO (não um bool), para que a Fase 4 possa
gravar o histórico apenas conectando mais um slot a este mesmo sinal.
"""
from PySide6.QtCore import QObject, QThread, Signal


class WorkerCore(QObject):
    concluiu = Signal(object)   # emite o Resultado* retornado pela função
    falhou = Signal(str)        # exceção INESPERADA (o core já trata erros esperados como dado)

    def __init__(self, funcao, *args, **kwargs):
        super().__init__()
        self._funcao = funcao
        self._args = args
        self._kwargs = kwargs

    def executar(self):
            try:
                resultado = self._funcao(*self._args, **self._kwargs)
            except SystemExit as e:
                # Defesa de fundo: se alguma função do core ainda usar sys.exit (em vez
                # de devolver Resultado*/ErroEntrada), o SystemExit NÃO herda de Exception
                # e mataria a thread silenciosamente, derrubando a janela. Convertemos em
                # falha tratável. (A correção definitiva é o core não usar sys.exit.)
                self.falhou.emit(f"o core encerrou inesperadamente (sys.exit: {e.code}).")
                return
            except BaseException as e:
                self.falhou.emit(f"{type(e).__name__}: {e}")
                return
            self.concluiu.emit(resultado)


def rodar_em_thread(dono, funcao, ao_concluir, ao_falhar, *args, **kwargs):
    """Cria thread+worker, conecta os sinais e dispara.

    Guarda as referências em `dono` (._thread/._worker) — sem isso o coletor de
    lixo do Python destrói a thread no meio da execução. Limpa no 'finished'.
    Retorna a thread (já iniciada).
    """
    thread = QThread()
    worker = WorkerCore(funcao, *args, **kwargs)
    worker.moveToThread(thread)

    thread.started.connect(worker.executar)
    worker.concluiu.connect(ao_concluir)
    worker.falhou.connect(ao_falhar)
    # encerra a thread quando o trabalho termina (sucesso ou falha)
    worker.concluiu.connect(thread.quit)
    worker.falhou.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    dono._thread = thread
    dono._worker = worker
    thread.start()
    return thread
