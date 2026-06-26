"""Objetos de resultado estruturado devolvidos pelos pontos de entrada do core.

A regra da camada: o core NÃO usa sys.exit nem print para comunicar resultado.
Ele monta e devolve um Resultado*; a CLI imprime e define o exit code, a GUI lê
o mesmo objeto. Erro vira dado (campo `erros`), não efeito colateral.
"""
from __future__ import annotations  # permite "str | None" / list[...] em Python 3.9
from dataclasses import dataclass, field


@dataclass
class ResultadoMapear:
    sucesso: bool
    conteudo: str                       # o mapa em Markdown (GUI exibe/copia sem reler o disco)
    caminho_saida: str | None
    arquivos_py: list[str]              # caminhos relativos
    arquivos_outros: list[str]
    linhas_por_arquivo: dict[str, int]  # rel -> nº de linhas (base do gráfico de evolução)
    total_linhas: int
    copiado: bool
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


@dataclass
class ItemExtraido:
    caminho: str
    tipo: str                 # "arquivo" | "classe" | "funcao"
    nome: str | None          # None para arquivo completo
    encontrado: bool          # confiável p/ arquivo completo; p/ nó depende do extrator (Fase 1+)


@dataclass
class ResultadoExtrair:
    sucesso: bool
    conteudo: str
    caminho_saida: str | None
    itens: list[ItemExtraido]
    total_linhas_extraidas: int
    instrucoes_anexadas: bool
    copiado: bool
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoArquivoAplicado:
    caminho: str                 # rel
    adicionadas: int             # de _contar_mudancas(diff)
    removidas: int
    diff: str                    # diff unificado (GUI renderiza nativo via _parsear_diff)
    gravado: bool
    backup_criado: bool
    erros: list[str] = field(default_factory=list)


@dataclass
class ResultadoAplicar:
    sucesso: bool
    aplicado: bool               # True = modo --aplicar (gravou); False = dry-run
    arquivos: list[ResultadoArquivoAplicado]
    total_adicionadas: int
    total_removidas: int
    caminho_patch: str | None    # se --diff
    caminho_html: str | None     # CLI ainda pode gerar; GUI ignora e usa os diffs
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)