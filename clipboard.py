"""Área de transferência sem dependências externas.

Usa apenas a stdlib, delegando para utilitários nativos de cada sistema via
`subprocess`. A ideia é fechar o ciclo com o chat da IA sem o passo manual de
"salvar a resposta num arquivo": `--copiar` joga a saída no clipboard e `--colar`
lê a resposta de lá.

Backends por plataforma:
  - Windows: PowerShell (Set-Clipboard / Get-Clipboard -Raw), com fallback p/ `clip`.
  - macOS:   pbcopy / pbpaste.
  - Linux/BSD: wl-copy/wl-paste (Wayland), xclip ou xsel (X11) — o primeiro disponível.

Em todos os casos o texto trafega como UTF-8, para não estropiar acentos e emojis
(o mapear e as instruções usam ambos).
"""

import sys
import shutil
import subprocess
import tempfile
from pathlib import Path


class ClipboardIndisponivel(RuntimeError):
    """Levantada quando não há backend de área de transferência utilizável."""


def _e_windows() -> bool:
    return sys.platform.startswith("win")


def _e_macos() -> bool:
    return sys.platform == "darwin"


def _powershell():
    """Retorna o executável do PowerShell disponível (pwsh ou powershell), ou None."""
    return shutil.which("pwsh") or shutil.which("powershell")


def _rodar(cmd, entrada=None, captura=False):
    """Executa `cmd`, opcionalmente enviando `entrada` (str) e/ou capturando stdout (str)."""
    try:
        proc = subprocess.run(
            cmd,
            input=entrada.encode("utf-8") if entrada is not None else None,
            stdout=subprocess.PIPE if captura else None,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as e:
        raise ClipboardIndisponivel(f"comando '{cmd[0]}' não encontrado.") from e
    except subprocess.CalledProcessError as e:
        detalhe = (e.stderr or b"").decode("utf-8", "replace").strip()
        raise ClipboardIndisponivel(f"falha ao executar '{cmd[0]}': {detalhe}") from e
    if captura:
        return proc.stdout.decode("utf-8", "replace")
    return None


# ----------------------------------------------------------------------------
# Windows (PowerShell preferido pela segurança de Unicode; clip como último recurso)
# ----------------------------------------------------------------------------
def _copiar_windows(texto: str):
    ps = _powershell()
    if ps:
        # Passa via arquivo temporário UTF-8 para evitar problemas de encoding/escape
        # ao injetar texto arbitrário (com aspas, quebras de linha, emojis) na linha de comando.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False, newline=""
        )
        try:
            tmp.write(texto)
            tmp.close()
            _rodar([
                ps, "-NoProfile", "-Command",
                f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 -LiteralPath '{tmp.name}')",
            ])
        finally:
            try:
                Path(tmp.name).unlink()
            except OSError:
                pass
        return
    # Fallback: `clip` existe em todo Windows, mas usa o code page legado e pode
    # estropiar acentos/emojis. Melhor que nada quando não há PowerShell.
    _rodar(["clip"], entrada=texto)


def _colar_windows() -> str:
    ps = _powershell()
    if not ps:
        raise ClipboardIndisponivel(
            "PowerShell não encontrado; não há como ler o clipboard no Windows sem ele."
        )
    # Força a saída em UTF-8 para o stdout chegar íntegro com acentos.
    return _rodar(
        [ps, "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        captura=True,
    )


# ----------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------
_LINUX_COPIAR = (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])
_LINUX_COLAR = (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"])
_DICA_LINUX = ("nenhum utilitário de clipboard encontrado. Instale um: "
               "wl-clipboard (Wayland) ou xclip/xsel (X11).")


def copiar(texto: str):
    """Copia `texto` para a área de transferência. Levanta ClipboardIndisponivel se falhar."""
    if _e_windows():
        return _copiar_windows(texto)
    if _e_macos():
        return _rodar(["pbcopy"], entrada=texto)
    for cmd in _LINUX_COPIAR:
        if shutil.which(cmd[0]):
            return _rodar(cmd, entrada=texto)
    raise ClipboardIndisponivel(_DICA_LINUX)


def colar() -> str:
    """Lê o texto atual da área de transferência. Levanta ClipboardIndisponivel se falhar."""
    if _e_windows():
        return _colar_windows()
    if _e_macos():
        return _rodar(["pbpaste"], captura=True)
    for cmd in _LINUX_COLAR:
        if shutil.which(cmd[0]):
            return _rodar(cmd, captura=True)
    raise ClipboardIndisponivel(_DICA_LINUX)


def disponivel() -> bool:
    """True se há algum backend de clipboard utilizável nesta máquina."""
    if _e_windows():
        return _powershell() is not None or shutil.which("clip") is not None
    if _e_macos():
        return shutil.which("pbcopy") is not None
    return any(shutil.which(cmd[0]) for cmd in _LINUX_COPIAR)