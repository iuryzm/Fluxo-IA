"""Teste do wrapper executar_sequencia_empacotado (empacota o retorno para o worker).

Não é Qt: exercita o empacotamento com runner fake (sem subprocess/PowerShell),
provando que o ResultadoSequencia carrega o res (com passos preenchidos in-place) e o
parou_em corretos.
"""
from pyresumidor.core import executor_sequencia as ex
from pyresumidor.core.resultados import (
    ResultadoAplicar, PassoComando, ResultadoComando, PassoPlano,
)


def _res_com_comando(comando="x", **kw):
    passo = PassoPlano(tipo="comando", ordem=0,
                       comando=PassoComando(comando=comando, **kw),
                       resultado_comando=ResultadoComando())
    return ResultadoAplicar(
        sucesso=True, aplicado=False, arquivos=[],
        total_adicionadas=0, total_removidas=0,
        caminho_patch=None, caminho_html=None,
        passos=[passo], sequenciado=True, estados_finais={})


def _fake_runner(exit_code=0, stdout="", stderr="", expirou=False):
    """Runner injetável (sem subprocess) na assinatura atual do executor:
    (comando, timeout, cwd, shell_exe, env)."""
    def runner(comando, timeout, cwd, shell_exe, env):
        return exit_code, stdout, stderr, expirou
    return runner


def test_empacotado_preenche_e_nao_diverge(tmp_path):
    """Comando ok (gate satisfeito): empacota res com ResultadoComando preenchido e
    parou_em=None."""
    res = _res_com_comando("qualquer", espera_exit=0)
    emp = ex.executar_sequencia_empacotado(
        res, str(tmp_path), lambda pc: True, runner=_fake_runner(exit_code=0))
    assert isinstance(emp, ex.ResultadoSequencia)
    assert emp.res is res
    assert emp.parou_em is None
    rc = res.passos[0].resultado_comando
    assert rc.executado is True and rc.divergiu is False


def test_empacotado_reporta_parada(tmp_path):
    """Comando que diverge (gate exit falha): parou_em aponta o passo 0."""
    res = _res_com_comando("qualquer", espera_exit=0)
    emp = ex.executar_sequencia_empacotado(
        res, str(tmp_path), lambda pc: True, runner=_fake_runner(exit_code=1))
    assert emp.parou_em == 0
    assert res.passos[0].resultado_comando.divergiu is True
