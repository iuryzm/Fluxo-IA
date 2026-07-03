"""Executor da sequência de passos (modo C): a ÚNICA parte que toca o mundo.

O core (aplicador.executar) PREPARA a lista de PassoPlano; este módulo a EXECUTA —
grava as edições no disco e roda os comandos via PowerShell, aplicando os gates
(critério ii) e parando na primeira divergência. Importar este módulo não tem efeito
colateral: nada roda no import. A execução só acontece quando executar_sequencia é
chamada explicitamente pela UI (CLI/GUI), que fornece o `confirmador` — o opt-in
humano obrigatório antes de cada comando.

Contexto de execução: os comandos rodam com `cwd` na raiz do PROJETO-ALVO e com o
ambiente montado por montar_ambiente() — se o alvo tiver um virtual environment,
o PATH do subprocesso é prefixado com ele, de modo que `pytest`, `python`, `pip`
etc. resolvem para o venv do alvo, e não para o ambiente onde o PyResumidor roda.

Segurança: não há sandbox. Passar o comando para `-Command` é execução arbitrária por
design; a proteção é o confirmador + o opt-in da UI, não restrição do que o comando faz.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path


def detectar_shell(preferido: str = "powershell"):
    """Executável de shell disponível, ou None. Reusa a detecção do clipboard.

    `preferido` vem do PassoComando ('powershell' ou 'pwsh'). Em ambos os casos
    tentamos pwsh (PowerShell Core, multiplataforma) primeiro e, no Windows, caímos
    para o powershell clássico. Sem nenhum, devolve None (a UI avisa).
    """
    if preferido == "pwsh":
        return shutil.which("pwsh")
    return shutil.which("pwsh") or shutil.which("powershell")


def _tem_interpretador(venv: Path) -> bool:
    """True se `venv` contém um interpretador Python no layout padrão de venv.

    Windows: <venv>/Scripts/python.exe. POSIX: <venv>/bin/python. Checar o
    interpretador (e não só a pasta) evita falsos positivos como uma pasta
    `env/` de variáveis de ambiente ou um venv quebrado/apagado pela metade.
    """
    if os.name == "nt":
        return (venv / "Scripts" / "python.exe").exists()
    return (venv / "bin" / "python").exists()


def _localizar_venv(projeto_path) -> Path | None:
    """Localiza o virtual environment do PROJETO-ALVO, se existir.

    Estratégia em duas etapas, sempre restrita ao 1º nível da raiz do projeto:
    1. Nomes convencionais, em ordem de prioridade: `.venv`, `venv`, `env`.
    2. Fallback: varre os subdiretórios (ordem alfabética, determinístico)
       procurando um `pyvenv.cfg` — o marcador que `python -m venv` cria na
       raiz de todo venv — para cobrir nomes fora da convenção.

    Em ambas as etapas o candidato só vale se tiver interpretador de verdade
    (_tem_interpretador). Devolve a raiz do venv (Path) ou None.
    """
    raiz = Path(projeto_path)

    for nome in (".venv", "venv", "env"):
        cand = raiz / nome
        if cand.is_dir() and _tem_interpretador(cand):
            return cand

    try:
        subdirs = sorted(p for p in raiz.iterdir() if p.is_dir())
    except OSError:
        return None
    for cand in subdirs:
        if (cand / "pyvenv.cfg").exists() and _tem_interpretador(cand):
            return cand
    return None


def montar_ambiente(projeto_path):
    """Monta o ambiente (env) para rodar comandos no contexto do PROJETO-ALVO.

    Se o alvo tem venv: prefixa o PATH com a pasta de executáveis do venv
    (Scripts no Windows, bin no POSIX), define VIRTUAL_ENV e REMOVE PYTHONHOME
    e PYTHONPATH herdados — isolando o subprocesso do ambiente onde o
    PyResumidor roda (é exatamente isso que faz `pytest` achar os pacotes do
    alvo, ex.: polars). Sem venv: devolve uma cópia intacta do ambiente atual.

    Devolve (env: dict, rotulo: str). O rotulo é texto legível que a UI exibe
    na confirmação, para o usuário saber ONDE o comando vai rodar antes do sim.
    """
    env = os.environ.copy()
    venv = _localizar_venv(projeto_path)
    if venv is None:
        return env, "ambiente do sistema (nenhum venv encontrado no projeto)"

    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(venv)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    return env, f"venv do projeto ({venv})"


def _rodar_comando_powershell(comando: str, timeout: int, cwd: str, shell_exe: str,
                              env: dict | None = None):
    """Runner REAL: roda `comando` via PowerShell. Único ponto que toca subprocess.

    `env` é o ambiente montado por montar_ambiente() (None = herda o do processo,
    comportamento antigo — mantido para chamadas diretas). Devolve a tupla neutra
    (exit_code, stdout, stderr, expirou). NÃO usa check=True — exit != 0 é dado
    (o gate precisa vê-lo), não exceção. Timeout mata o processo e marca
    expirou=True. É esta função que os testes substituem por um runner fake.
    """
    try:
        proc = subprocess.run(
            [shell_exe, "-NoProfile", "-Command", comando],
            capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        err = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", "replace")
        return None, out or "", err or "", True


def _avaliar_gates(pc, exit_code, stdout: str, stderr: str, expirou: bool):
    """Aplica os gates (ii) a um resultado de comando. Lógica pura, sem efeito.

    Devolve (divergiu: bool, motivo: str). Ordem: timeout primeiro (mais grave),
    depois espera_exit, depois espera_conter (em stdout+stderr). Sem nenhum gate,
    nunca diverge (comando informativo).
    """
    if expirou:
        return True, f"tempo esgotado (timeout) ao rodar: {pc.comando}"
    if pc.espera_exit is not None and exit_code != pc.espera_exit:
        return True, f"exit code {exit_code} != esperado {pc.espera_exit}"
    if pc.espera_conter is not None and pc.espera_conter not in (stdout + stderr):
        return True, f"saída não contém o esperado: {pc.espera_conter!r}"
    return False, ""


def _gravar_edicao(alvo: Path, texto: str, sem_backup: bool) -> bool:
    """Grava uma edição no disco (com .bak por padrão). Devolve se criou backup."""
    backup = False
    if alvo.exists() and not sem_backup:
        shutil.copy2(alvo, alvo.with_suffix(alvo.suffix + ".bak"))
        backup = True
    alvo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = texto if texto.endswith("\n") else texto + "\n"
    alvo.write_text(conteudo, encoding="utf-8")
    return backup


def executar_sequencia(passos, projeto_path, confirmador, estados_finais,
                       runner=None, timeout_padrao: int = 60, sem_backup: bool = False):
    """Percorre os passos preparados e os EXECUTA em ordem, parando na 1ª divergência.

    - passos: lista de PassoPlano (o core preparou; ordem = ordem do plano).
    - projeto_path: raiz onde gravar e rodar (cwd dos comandos). O ambiente dos
      comandos é montado UMA vez a partir daqui (montar_ambiente): venv do alvo
      no PATH quando existir, e o rotulo é registrado em ResultadoComando.ambiente.
    - confirmador: callable(PassoComando) -> bool. Chamado antes de CADA comando; um
      comando só roda se devolver True. Recusar PARA a sequência (os passos seguintes
      podem depender dele). É o opt-in humano obrigatório.
    - estados_finais: dict {rel: texto_final} calculado pelo core, com o conteúdo a
      gravar em cada passo de edição (o core acumulou; aqui só persistimos).
    - runner: injeta o executor de comando (para testes). Default = PowerShell real.
      Assinatura: runner(comando, timeout, cwd, shell_exe, env).
    - timeout_padrao: usado quando o passo não especifica timeout.
    - sem_backup: não cria .bak ao gravar.

    Devolve (passos, parou_em): os PassoPlano têm seus ResultadoComando preenchidos;
    parou_em é o índice do passo que abortou (ou None se rodou até o fim).
    Passos após a parada ficam executado=False.
    """
    if runner is None:
        runner = _rodar_comando_powershell

    env, rotulo_ambiente = montar_ambiente(projeto_path)
    parou_em = None

    for idx, passo in enumerate(passos):
        if parou_em is not None:
            continue  # já paramos: passos seguintes não executam (ResultadoComando fica vazio)

        if passo.tipo == "edicao":
            alvo = Path(projeto_path) / passo.caminho
            texto = estados_finais.get(passo.caminho)
            if texto is None:
                continue  # nada a gravar (edição sem estado — não deveria ocorrer)
            _gravar_edicao(alvo, texto, sem_backup)
            continue

        # passo de comando
        pc = passo.comando
        rc = passo.resultado_comando

        if not confirmador(pc):
            rc.executado = False
            rc.motivo_divergencia = "comando recusado na confirmação; sequência interrompida."
            parou_em = idx
            continue

        shell_exe = detectar_shell(pc.shell)
        if shell_exe is None:
            rc.executado = False
            rc.divergiu = True
            rc.motivo_divergencia = "PowerShell não encontrado (nem pwsh nem powershell)."
            parou_em = idx
            continue

        timeout = pc.timeout if pc.timeout is not None else timeout_padrao
        exit_code, stdout, stderr, expirou = runner(
            pc.comando, timeout, str(projeto_path), shell_exe, env)

        rc.executado = True
        rc.ambiente = rotulo_ambiente
        rc.exit_code = exit_code
        rc.stdout = stdout
        rc.stderr = stderr
        rc.expirou = expirou

        divergiu, motivo = _avaliar_gates(pc, exit_code, stdout, stderr, expirou)
        rc.divergiu = divergiu
        rc.motivo_divergencia = motivo
        if divergiu:
            parou_em = idx

    return passos, parou_em


class ResultadoSequencia:
    """Empacota o retorno de duas partes de executar_sequencia num objeto único.

    O WorkerCore da GUI emite UM objeto pelo sinal `concluiu`; como executar_sequencia
    devolve (passos, parou_em) e muta os passos in-place (preenche os ResultadoComando),
    guardamos aqui o `res` (com os passos já preenchidos) e o `parou_em`, para o slot de
    conclusão desempacotar sem depender de tupla no sinal.
    """
    def __init__(self, res, parou_em):
        self.res = res
        self.parou_em = parou_em


def executar_sequencia_empacotado(res, projeto_path, confirmador, timeout_padrao=60,
                                  sem_backup=False, runner=None):
    """Wrapper de executar_sequencia que devolve UM ResultadoSequencia (para o worker).

    Chama executar_sequencia com os passos e estados que o core já preparou em `res`
    (res.passos, res.estados_finais). Como executar_sequencia muta res.passos in-place,
    o `res` devolvido já carrega os ResultadoComando preenchidos. `runner` é repassado
    (default = PowerShell real) para permitir teste sem subprocess. Não é Qt.
    """
    _passos, parou_em = executar_sequencia(
        res.passos, projeto_path, confirmador, res.estados_finais,
        runner=runner, timeout_padrao=timeout_padrao, sem_backup=sem_backup)
    return ResultadoSequencia(res, parou_em)
