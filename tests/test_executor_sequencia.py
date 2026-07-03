"""Testes do executor de sequência (modo C).

A lógica de gate/parada/percurso é testada de forma PORTÁVEL via runner injetado
(fake, sem subprocess). Um teste de fumaça roda o PowerShell REAL, mas só quando
pwsh/powershell existe na máquina (skip caso contrário) — assim a suíte não depende
de shell para passar.

Também cobre o contexto de execução do projeto-alvo: detecção do venv
(_localizar_venv), montagem do ambiente (montar_ambiente: PATH prefixado,
VIRTUAL_ENV, limpeza de PYTHONHOME/PYTHONPATH) e a injeção do env/cwd no runner.
Os runners fake seguem a assinatura atual: (comando, timeout, cwd, shell_exe, env).
"""
import os
import shutil
import pytest
from pathlib import Path
from pyresumidor.core import executor_sequencia as ex
from pyresumidor.core.resultados import PassoComando, ResultadoComando, PassoPlano


def _passo_comando(comando, ordem=0, **kw):
    return PassoPlano(tipo="comando", ordem=ordem,
                      comando=PassoComando(comando=comando, **kw),
                      resultado_comando=ResultadoComando())


def _passo_edicao(caminho, ordem=0):
    return PassoPlano(tipo="edicao", ordem=ordem, caminho=caminho)


def _sempre_sim(_pc):
    return True


def _fake_runner(exit_code=0, stdout="", stderr="", expirou=False):
    """Runner injetável que não toca subprocess; devolve o que mandarmos."""
    def runner(comando, timeout, cwd, shell_exe, env):
        return exit_code, stdout, stderr, expirou
    return runner


def _criar_venv_fake(raiz: Path, nome: str) -> Path:
    """Simula um venv válido no layout da plataforma atual (com pyvenv.cfg)."""
    venv = raiz / nome
    if os.name == "nt":
        (venv / "Scripts").mkdir(parents=True)
        (venv / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    else:
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("", encoding="utf-8")
    (venv / "pyvenv.cfg").write_text("home = fake\n", encoding="utf-8")
    return venv


# --- _avaliar_gates (lógica pura) ---

def test_gate_exit_ok_nao_diverge():
    pc = PassoComando(comando="x", espera_exit=0)
    div, _ = ex._avaliar_gates(pc, 0, "", "", False)
    assert div is False


def test_gate_exit_diferente_diverge():
    pc = PassoComando(comando="x", espera_exit=0)
    div, motivo = ex._avaliar_gates(pc, 1, "", "", False)
    assert div is True and "exit" in motivo


def test_gate_conter_presente_nao_diverge():
    pc = PassoComando(comando="x", espera_conter="OK")
    div, _ = ex._avaliar_gates(pc, 0, "tudo OK aqui", "", False)
    assert div is False


def test_gate_conter_ausente_diverge():
    pc = PassoComando(comando="x", espera_conter="OK")
    div, motivo = ex._avaliar_gates(pc, 0, "falhou", "", False)
    assert div is True and "contém" in motivo


def test_gate_timeout_sempre_diverge():
    pc = PassoComando(comando="x", espera_exit=0)
    div, motivo = ex._avaliar_gates(pc, None, "", "", True)
    assert div is True and "timeout" in motivo


def test_sem_gate_nunca_diverge():
    pc = PassoComando(comando="x")   # sem espera_*
    div, _ = ex._avaliar_gates(pc, 137, "qualquer", "coisa", False)
    assert div is False


# --- executar_sequencia (orquestração, runner fake) ---

def test_sequencia_para_no_gate_que_diverge(tmp_path):
    """Comando que diverge para a sequência; passo seguinte não executa."""
    passos = [
        _passo_comando("falha", ordem=0, espera_exit=0),
        _passo_comando("nunca", ordem=1),
    ]
    runner = _fake_runner(exit_code=1)   # diverge (esperava 0)
    passos, parou = ex.executar_sequencia(passos, tmp_path, _sempre_sim, {}, runner=runner)
    assert parou == 0
    assert passos[0].resultado_comando.divergiu is True
    assert passos[1].resultado_comando.executado is False   # não chegou a rodar


def test_sequencia_recusa_para(tmp_path):
    """Confirmador que nega PARA a sequência."""
    passos = [_passo_comando("perigoso", ordem=0), _passo_comando("depois", ordem=1)]
    passos, parou = ex.executar_sequencia(passos, tmp_path, lambda pc: False, {},
                                          runner=_fake_runner())
    assert parou == 0
    assert passos[0].resultado_comando.executado is False
    assert "recusado" in passos[0].resultado_comando.motivo_divergencia
    assert passos[1].resultado_comando.executado is False


def test_sequencia_grava_edicao_e_roda_comando(tmp_path):
    """Edição é gravada no disco; comando seguinte roda (runner fake) e não diverge."""
    (tmp_path / "a.py").write_text("velho\n", encoding="utf-8")
    passos = [_passo_edicao("a.py", ordem=0), _passo_comando("ok", ordem=1, espera_exit=0)]
    estados = {"a.py": "novo\n"}
    passos, parou = ex.executar_sequencia(passos, tmp_path, _sempre_sim, estados,
                                          runner=_fake_runner(exit_code=0), sem_backup=True)
    assert parou is None
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "novo\n"   # gravou
    assert passos[1].resultado_comando.executado is True
    assert passos[1].resultado_comando.divergiu is False


def test_sequencia_edicao_cria_backup(tmp_path):
    """Gravação de edição cria .bak por padrão."""
    (tmp_path / "a.py").write_text("velho\n", encoding="utf-8")
    passos = [_passo_edicao("a.py", ordem=0)]
    ex.executar_sequencia(passos, tmp_path, _sempre_sim, {"a.py": "novo\n"})
    assert (tmp_path / "a.py.bak").exists()
    assert (tmp_path / "a.py.bak").read_text(encoding="utf-8") == "velho\n"


def test_sequencia_completa_sem_gate(tmp_path):
    """Comando sem gate roda e a sequência segue até o fim (parou_em=None)."""
    passos = [_passo_comando("informativo", ordem=0)]   # sem espera_*
    passos, parou = ex.executar_sequencia(passos, tmp_path, _sempre_sim, {},
                                          runner=_fake_runner(exit_code=42))
    assert parou is None
    assert passos[0].resultado_comando.executado is True
    assert passos[0].resultado_comando.divergiu is False   # sem gate, exit 42 não importa


# --- venv do projeto-alvo: detecção e montagem do ambiente ---

def test_localizar_venv_nome_convencional(tmp_path):
    esperado = _criar_venv_fake(tmp_path, "venv")
    assert ex._localizar_venv(tmp_path) == esperado


def test_localizar_venv_prioridade_ponto_venv(tmp_path):
    """Com `.venv` e `venv` presentes, `.venv` vence (ordem de prioridade)."""
    _criar_venv_fake(tmp_path, "venv")
    esperado = _criar_venv_fake(tmp_path, ".venv")
    assert ex._localizar_venv(tmp_path) == esperado


def test_localizar_venv_fallback_pyvenv_cfg(tmp_path):
    """Nome fora da convenção é achado pelo fallback via pyvenv.cfg."""
    esperado = _criar_venv_fake(tmp_path, "meuambiente")
    assert ex._localizar_venv(tmp_path) == esperado


def test_localizar_venv_ignora_pasta_sem_interpretador(tmp_path):
    """Pasta com nome convencional mas sem interpretador não conta como venv."""
    (tmp_path / "venv").mkdir()
    assert ex._localizar_venv(tmp_path) is None


def test_localizar_venv_ausente_devolve_none(tmp_path):
    assert ex._localizar_venv(tmp_path) is None


def test_montar_ambiente_prefixa_path_e_limpa(tmp_path, monkeypatch):
    """Com venv: PATH prefixado, VIRTUAL_ENV definido, PYTHONHOME/PYTHONPATH removidos."""
    monkeypatch.setenv("PYTHONHOME", "contaminado")
    monkeypatch.setenv("PYTHONPATH", "contaminado")
    venv = _criar_venv_fake(tmp_path, ".venv")

    env, rotulo = ex.montar_ambiente(tmp_path)

    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    assert env["PATH"].startswith(str(bin_dir) + os.pathsep)
    assert env["VIRTUAL_ENV"] == str(venv)
    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert rotulo.startswith("venv do projeto")


def test_montar_ambiente_sem_venv_copia_intacta(tmp_path, monkeypatch):
    """Sem venv: cópia do ambiente atual, sem mexer em PATH nem PYTHONPATH."""
    monkeypatch.setenv("PYTHONPATH", "mantem")
    env, rotulo = ex.montar_ambiente(tmp_path)
    assert env["PYTHONPATH"] == "mantem"
    assert env["PATH"] == os.environ["PATH"]
    assert rotulo.startswith("ambiente do sistema")


def test_executar_sequencia_injeta_env_e_cwd_no_runner(tmp_path, monkeypatch):
    """Ponta a ponta com runner fake: o comando recebe cwd do projeto-alvo e o env
    do venv, e ResultadoComando.ambiente registra o rotulo."""
    venv = _criar_venv_fake(tmp_path, ".venv")
    monkeypatch.setattr(ex, "detectar_shell", lambda pref: "fake-shell")
    capturado = {}

    def runner_captura(comando, timeout, cwd, shell_exe, env):
        capturado["cwd"] = cwd
        capturado["env"] = env
        return 0, "ok", "", False

    passo = _passo_comando("echo oi", ordem=0)

    _passos, parou_em = ex.executar_sequencia(
        [passo], tmp_path, _sempre_sim, {}, runner=runner_captura)

    assert parou_em is None
    assert capturado["cwd"] == str(tmp_path)
    assert capturado["env"]["VIRTUAL_ENV"] == str(venv)
    assert passo.resultado_comando.executado is True
    assert passo.resultado_comando.ambiente.startswith("venv do projeto")


# --- fumaça: PowerShell REAL (só se existir) ---

@pytest.mark.skipif(
    not (shutil.which("pwsh") or shutil.which("powershell")),
    reason="PowerShell não instalado nesta máquina.")
def test_fumaca_powershell_real(tmp_path):
    """Roda um comando trivial no PowerShell de verdade e confere a captura."""
    passos = [_passo_comando("Write-Output ola", ordem=0, espera_conter="ola")]
    passos, parou = ex.executar_sequencia(passos, tmp_path, _sempre_sim, {})
    rc = passos[0].resultado_comando
    assert rc.executado is True
    assert parou is None
    assert "ola" in rc.stdout
