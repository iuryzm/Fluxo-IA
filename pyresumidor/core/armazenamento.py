"""Local único de gravação dos artefatos de runtime do PyResumidor.

Decisão: os dados de cada projeto-alvo são gravados DENTRO da instalação do
PyResumidor (subpasta 'dados/'), não no diretório do projeto-alvo. Motivo: em
ambientes onde o projeto-alvo é apagado periodicamente (ex.: VM com faxina), os
artefatos não-versionados se perderiam. Centralizar aqui significa que, se um dia
o destino precisar mudar (ex.: instalação não-editável em site-packages, que é
read-only), troca-se num só lugar.

Cada projeto-alvo recebe uma subpasta estável derivada do caminho absoluto do seu
.gitignore — assim o mesmo projeto sempre cai na mesma pasta, mesmo renomeado.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path


def diretorio_dados() -> Path:
    """Raiz dos dados de runtime: <pacote>/dados/. Criada se não existir."""
    # __file__ = <pacote>/core/armazenamento.py  ->  parents[1] = <pacote>
    base = Path(__file__).resolve().parents[1] / "dados"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _slug(texto: str) -> str:
    """Reduz um texto a algo seguro para nome de pasta (sem perder legibilidade)."""
    limpo = re.sub(r"[^A-Za-z0-9._-]", "_", texto).strip("_")
    return (limpo or "projeto")[:40]


def id_projeto(gitignore_path: str) -> str:
    """Identificador estável de um projeto a partir do caminho do seu .gitignore.

    Formato: <nome-da-pasta-raiz>_<hash-curto>. O hash garante unicidade; o
    prefixo legível deixa a pasta reconhecível ao abrir 'dados/' no explorador.
    """
    p = Path(gitignore_path).resolve()
    raiz = p.parent
    h = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:8]
    return f"{_slug(raiz.name)}_{h}"


def dir_projeto(gitignore_path: str) -> Path:
    """Subpasta de dados de um projeto-alvo. Criada se não existir."""
    d = diretorio_dados() / "projetos" / id_projeto(gitignore_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def caminho_mapa(gitignore_path: str) -> Path:
    """Onde o Mapear grava o .md daquele projeto."""
    return dir_projeto(gitignore_path) / "mapa.md"


def caminho_entrada_extrair(gitignore_path: str) -> Path:
    """Onde a GUI grava a resposta da IA usada no Extrair (entrada do comando).

    Persistir aqui atende ao requisito de histórico: a entrada de cada execução
    sobrevive ao fechamento da janela e à limpeza do projeto-alvo.
    """
    return dir_projeto(gitignore_path) / "entrada_extrair.md"


def caminho_saida_extrair(gitignore_path: str) -> Path:
    """Onde o Extrair grava o Markdown com os trechos extraídos (saída do comando)."""
    return dir_projeto(gitignore_path) / "extracao.md"


def caminho_entrada_aplicar(gitignore_path: str) -> Path:
    """Onde a GUI grava a resposta da IA usada no Aplicar (plano + blocos).

    Persistida como entrada do comando (histórico da Fase 4). É também a fonte que
    a aplicação real consome — garante que se grava exatamente o que foi simulado.
    """
    return dir_projeto(gitignore_path) / "entrada_aplicar.md"
