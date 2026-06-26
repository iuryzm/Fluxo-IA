"""Workers da GUI (QThread) que rodam o core sem travar a interface."""
from pyresumidor.gui.workers.worker_core import WorkerCore, rodar_em_thread

__all__ = ["WorkerCore", "rodar_em_thread"]
