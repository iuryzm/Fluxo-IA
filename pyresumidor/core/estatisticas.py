"""Agregação do histórico de um projeto em estatísticas (stdlib pura).

Lê o histórico que o armazenamento já grava (lista de execuções com comando, ok,
resumo, ts) e produz números prontos para a GUI: contadores por comando, totais de
linhas alteradas e a série temporal de tamanho do projeto (para o gráfico de
evolução). Não coleta nada novo — só agrega o que a Fase 4 acumulou.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from pyresumidor.core.armazenamento import listar_historico


@dataclass
class EstatisticasProjeto:
    total_execucoes: int
    por_comando: dict           # {"mapear": 3, "extrair": 5, "aplicar": 2}
    total_adicionadas: int      # soma das linhas + dos Aplicar
    total_removidas: int        # soma das linhas - dos Aplicar
    evolucao_linhas: list       # [(ts, total_linhas), ...] cronológico (gráfico)
    evolucao_arquivos: list     # [(ts, n_py + n_outros), ...] cronológico (gráfico)
    ultimo_mapa: dict = field(default_factory=dict)  # resumo do Mapear mais recente


def calcular(gitignore_path: str) -> EstatisticasProjeto:
    """Agrega o histórico do projeto. Devolve zeros/listas vazias se não houver nada."""
    hist = listar_historico(gitignore_path)  # mais recente primeiro

    por_comando: dict = {}
    add = rem = 0
    evolucao = []           # (ts, total_linhas) dos Mapear
    evolucao_arq = []       # (ts, n_py + n_outros) dos Mapear
    ultimo_mapa: dict = {}

    for entrada in hist:
        if not isinstance(entrada, dict):
            continue
        cmd = entrada.get("comando", "?")
        por_comando[cmd] = por_comando.get(cmd, 0) + 1
        resumo = entrada.get("resumo") or {}
        ts = entrada.get("ts")

        if cmd == "aplicar":
            add += int(resumo.get("adicionadas", 0) or 0)
            rem += int(resumo.get("removidas", 0) or 0)

        if cmd == "mapear":
            tl = resumo.get("total_linhas")
            if ts is not None and tl is not None:
                evolucao.append((ts, int(tl)))
                n_arq = int(resumo.get("n_py", 0) or 0) + int(resumo.get("n_outros", 0) or 0)
                evolucao_arq.append((ts, n_arq))
            if not ultimo_mapa:   # hist decrescente -> 1º mapear visto é o mais recente
                ultimo_mapa = dict(resumo)

    evolucao.sort(key=lambda par: par[0])
    evolucao_arq.sort(key=lambda par: par[0])

    return EstatisticasProjeto(
        total_execucoes=len(hist),
        por_comando=por_comando,
        total_adicionadas=add,
        total_removidas=rem,
        evolucao_linhas=evolucao,
        evolucao_arquivos=evolucao_arq,
        ultimo_mapa=ultimo_mapa,
    )
