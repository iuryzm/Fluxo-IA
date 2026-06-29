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
import json
import re
import time
from pathlib import Path

_CONFIG_PADRAO = {"max_recentes": 10, "max_historico": 50}


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


def _ler_json(caminho: Path, padrao):
    """Lê um JSON com fallback robusto: arquivo ausente ou corrompido devolve o
    padrão em vez de quebrar. Persistência nunca deve derrubar o app (ex.: escrita
    interrompida pela faxina da VM)."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return padrao


def _gravar_json(caminho: Path, dados) -> None:
    """Grava JSON de forma atômica: escreve num temporário e renomeia. Evita deixar
    um arquivo meio-escrito (e portanto corrompido) se o processo morrer no meio."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(caminho)


def caminho_config() -> Path:
    """Arquivo de PREFERÊNCIAS do usuário (config.json). Separado do índice de
    recentes (que é estado): resetar um não afeta o outro."""
    return diretorio_dados() / "config.json"


def carregar_config() -> dict:
    """Configuração efetiva: padrões sobrescritos pelo que houver no config.json."""
    cfg = dict(_CONFIG_PADRAO)
    cfg.update(_ler_json(caminho_config(), {}))
    return cfg


def salvar_config(cfg: dict) -> None:
    """Persiste a configuração (mescla sobre os padrões para nunca perder chaves)."""
    completa = dict(_CONFIG_PADRAO)
    completa.update(cfg)
    _gravar_json(caminho_config(), completa)


def salvar_projeto(gitignore_path: str, dados: dict) -> None:
    """Grava o estado de um projeto (dict simples) em dados/projetos/<id>/projeto.json.

    Recebe um dict (não um objeto de GUI) para manter o core independente da camada
    de interface: a GUI converte seu Projeto em dict na fronteira.
    """
    _gravar_json(dir_projeto(gitignore_path) / "projeto.json", dados)


def carregar_projeto(gitignore_path: str) -> dict:
    """Lê o estado de um projeto. Devolve {} se ainda não houver nada gravado."""
    return _ler_json(dir_projeto(gitignore_path) / "projeto.json", {})


def registrar_recente(gitignore_path: str, nome: str) -> None:
    """Registra um projeto na lista de recentes (estado, em indice.json).

    O mais recente fica no topo; entradas repetidas (mesmo .gitignore) sobem em vez
    de duplicar; a lista é truncada em max_recentes (configurável em config.json).
    """
    caminho = diretorio_dados() / "indice.json"
    lista = _ler_json(caminho, [])
    if not isinstance(lista, list):
        lista = []
    alvo = str(Path(gitignore_path).resolve())
    # remove ocorrência anterior do mesmo projeto (vai voltar ao topo)
    lista = [e for e in lista if e.get("gitignore") != alvo]
    lista.insert(0, {"gitignore": alvo, "nome": nome, "ts": time.time()})
    limite = carregar_config().get("max_recentes", 10)
    _gravar_json(caminho, lista[:limite])


def listar_recentes() -> list:
    """Lista de recentes (mais recente primeiro). Filtra entradas cujo .gitignore
    não existe mais no disco — não adianta oferecer um projeto que sumiu."""
    lista = _ler_json(diretorio_dados() / "indice.json", [])
    if not isinstance(lista, list):
        return []
    return [e for e in lista if e.get("gitignore") and Path(e["gitignore"]).exists()]


def registrar_historico(gitignore_path: str, comando: str, ok: bool, resumo: dict) -> None:
    """Anexa uma execução ao histórico do projeto (em projeto.json).

    Faz MERGE: lê o projeto.json inteiro, mexe só na chave 'historico' e regrava o
    todo — para não apagar outros campos do projeto. A entrada mais recente fica no
    topo; a lista é truncada em max_historico (config.json). O 'resumo' é um dict
    de números simples (linhas, itens, +/−) montado por quem chama — é o dado bruto
    que a Fase 5 vai agregar em estatísticas.
    """
    proj = carregar_projeto(gitignore_path)
    if not isinstance(proj, dict):
        proj = {}
    hist = proj.get("historico")
    if not isinstance(hist, list):
        hist = []
    hist.insert(0, {"ts": time.time(), "comando": comando, "ok": bool(ok), "resumo": resumo})
    limite = carregar_config().get("max_historico", 50)
    proj["historico"] = hist[:limite]
    salvar_projeto(gitignore_path, proj)


def listar_historico(gitignore_path: str) -> list:
    """Histórico de execuções do projeto (mais recente primeiro). [] se não houver."""
    proj = carregar_projeto(gitignore_path)
    if not isinstance(proj, dict):
        return []
    hist = proj.get("historico")
    return hist if isinstance(hist, list) else []
