"""Ponto de entrada da CLI: despacha para mapear / extrair / aplicar.

Os módulos do core devolvem objetos Resultado*; esta camada é a única que
imprime e define o código de saída do processo.
"""

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from pyresumidor.core import (
    mapear,
    extrator,
    aplicador,
    executor_sequencia,
)
from pyresumidor.core.aplicador import _gerar_html_diff


def _registrar_mapear(sub):
    """Registra os argumentos do subcomando 'mapear'."""
    p = sub.add_parser(
        "mapear",
        help="Gera o mapa de arquitetura do projeto.",
        description="Gera um resumo do código Python baseado no .gitignore.",
    )
    p.add_argument("gitignore_path", help="Caminho para o .gitignore do projeto alvo.")
    p.add_argument("output_path", help="Caminho e nome do arquivo .md de saída.")
    p.add_argument("--linhas-config", type=int, default=20,
                   help="Nº de linhas de prévia para arquivos de config/outros. 0 = sem prévia (default: 20).")
    p.add_argument("--excluir", nargs="*", default=[], metavar="PADRAO",
                   help="Padrões glob a NÃO incluir no resumo (soma-se ao .resumoignore).")
    p.add_argument("--copiar", action="store_true",
                   help="Também copia o mapa para a área de transferência.")
    return p


def _registrar_extrair(sub):
    """Registra os argumentos do subcomando 'extrair'."""
    p = sub.add_parser(
        "extrair",
        help="Extrai os trechos de código pedidos pela IA.",
        description="Extrai código-fonte baseado em um JSON da IA.",
    )
    p.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta (JSON) da IA. Opcional com --colar.")
    p.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto.")
    p.add_argument("output_path", nargs="?", help="Arquivo .md de saída com os códigos extraídos.")
    p.add_argument("--sem-instrucoes", action="store_true",
                   help="Não anexa ao fim da saída as instruções de formato do aplicador.")
    p.add_argument("--colar", action="store_true",
                   help="Lê a resposta da IA da área de transferência (dispensa 'resposta_ia').")
    p.add_argument("--copiar", action="store_true",
                   help="Copia a saída (código extraído) para a área de transferência.")
    return p


def _registrar_aplicar(sub):
    """Registra os argumentos do subcomando 'aplicar'."""
    p = sub.add_parser(
        "aplicar",
        help="Aplica as alterações propostas pela IA.",
        description="Aplica alterações da IA por nome via AST (e edições por âncora).",
    )
    p.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta da IA (plano + blocos).")
    p.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto.")
    p.add_argument("--aplicar", action="store_true", help="Grava as alterações (default: dry-run).")
    p.add_argument("--diff", dest="diff_path", default=None, help="Salva o patch unificado combinado neste caminho.")
    p.add_argument("--sem-backup", action="store_true", help="Não cria arquivos .bak ao gravar.")
    p.add_argument("--colar", action="store_true",
                   help="Lê a resposta da IA da área de transferência (dispensa 'resposta_ia').")
    p.add_argument("--html-diff", nargs="?", const="", default=None, metavar="ARQUIVO.html",
                   help="Gera uma página HTML com os diffs coloridos e abre no navegador "
                        "(sem valor = arquivo temporário).")
    p.add_argument("--instrucoes", action="store_true",
                   help="Imprime as instruções para colar no chat com a IA e sai.")
    p.add_argument("--permitir-comandos", action="store_true",
                   help="OPT-IN: autoriza a execução de comandos (acao 'comando') do plano. "
                        "Sem esta flag, um plano com comandos é recusado. Comandos rodam na "
                        "SUA máquina via PowerShell, com confirmação por comando.")
    p.add_argument("--confirmar-lote", action="store_true",
                   help="Confirma todos os comandos de uma vez (mostra a lista e pede um único "
                        "sim), em vez de perguntar um a um. Requer --permitir-comandos.")
    p.add_argument("--timeout-comando", type=int, default=60, metavar="SEG",
                   help="Timeout (segundos) padrão por comando quando o plano não especifica "
                        "(default: 60).")
    return p


def _exibir_mapear(res) -> int:
    if not res.sucesso:
        for e in res.erros:
            print(f"\033[31m❌ {e}\033[0m")
        return 1
    if not res.conteudo:
        for a in res.avisos:
            print(f"\033[33m⚠️ {a}\033[0m")
        return 0
    print(f"✅ Mapa gerado em: {res.caminho_saida}")
    print(f"   {len(res.arquivos_py)} .py · {len(res.arquivos_outros)} outros · {res.total_linhas} linhas no total")
    if res.copiado:
        print("📋 Copiado para a área de transferência.")
    for a in res.avisos:
        print(f"\033[33m⚠️ {a}\033[0m")
    return 0


def _exibir_extrair(res) -> int:
    if not res.sucesso:
        for e in res.erros:
            print(f"\033[31m❌ {e}\033[0m")
        return 1
    print(f"✅ Extração concluída em: {res.caminho_saida}")
    achados = sum(1 for i in res.itens if i.encontrado)
    print(f"   {achados}/{len(res.itens)} item(ns) confirmado(s) como localizado(s).")
    if res.instrucoes_anexadas:
        print("   (instruções do aplicador anexadas)")
    if res.copiado:
        print("📋 Copiado para a área de transferência.")
    for a in res.avisos:
        print(f"\033[33m⚠️ {a}\033[0m")
    return 0


def _exibir_aplicar(res, projeto_path, html_diff) -> int:
    if not res.sucesso:
        for e in res.erros:
            print(f"\033[31m❌ {e}\033[0m")
        return 1

    print(f"📂 Projeto: {projeto_path}")
    print("\033[1;32m✍️  MODO APLICAR (gravou)\033[0m" if res.aplicado
          else "\033[1;33m👀 MODO DRY-RUN (nada gravado)\033[0m")
    print()

    erros_arquivos = []
    for arq in res.arquivos:
        if arq.diff:
            print(f"\033[1;34m📝 {arq.caminho}\033[0m")
            for linha in arq.diff.splitlines():
                if linha.startswith("+") and not linha.startswith("+++"):
                    print(f"\033[32m{linha}\033[0m")
                elif linha.startswith("-") and not linha.startswith("---"):
                    print(f"\033[31m{linha}\033[0m")
                elif linha.startswith("@@"):
                    print(f"\033[36m{linha}\033[0m")
                else:
                    print(linha)
            if res.aplicado and arq.gravado:
                sufixo = " (backup .bak criado)" if arq.backup_criado else ""
                print(f"   \033[32m✅ gravado{sufixo}\033[0m\n")
            else:
                print()
        else:
            print(f"➖ {arq.caminho}: nenhuma mudança gerada.\n")
        erros_arquivos.extend(arq.erros)

    if res.caminho_patch:
        print(f"\033[32m💾 Patch combinado salvo em: {res.caminho_patch}\033[0m")
        print(f"   git apply {res.caminho_patch}")

    todos_erros = list(res.erros) + erros_arquivos
    if todos_erros:
        print("\n\033[1;31m⚠️ Avisos/erros:\033[0m")
        for e in todos_erros:
            print(f"   \033[31m- {e}\033[0m")
    for a in res.avisos:
        print(f"\033[33m⚠️ {a}\033[0m")

    if html_diff is not None:
        diffs_arquivos = [(a.caminho, a.diff) for a in res.arquivos if a.diff]
        if diffs_arquivos or todos_erros:
            pagina = _gerar_html_diff(diffs_arquivos, projeto_path, res.aplicado, todos_erros)
            if html_diff:
                destino = Path(html_diff).resolve()
                destino.parent.mkdir(parents=True, exist_ok=True)
            else:
                tmp = tempfile.NamedTemporaryFile(prefix="aplicador_diff_", suffix=".html", delete=False)
                tmp.close()
                destino = Path(tmp.name)
            destino.write_text(pagina, encoding="utf-8")
            print(f"\n🌐 Diff em HTML salvo em: {destino}")
            try:
                if webbrowser.open(destino.as_uri()):
                    print("   Abrindo no navegador...")
                else:
                    print("   (não consegui abrir o navegador; abra o arquivo manualmente.)")
            except Exception:
                print("   (não consegui abrir o navegador; abra o arquivo manualmente.)")
        else:
            print("\n🌐 --html-diff: nada para mostrar (nenhuma mudança gerada).")

    if not res.aplicado and any(a.diff for a in res.arquivos):
        print("\n\033[33mℹ️ Dry-run. Use --aplicar para gravar, ou --diff arquivo.patch para salvar o patch.\033[0m")
    return 0


def main(argv=None) -> int:
    """Roteia os argumentos, despacha o comando e devolve o código de saída."""
    parser = argparse.ArgumentParser(
        prog="pyresumidor",
        description="Toolkit de edição de código assistida por IA (pipeline mapear → extrair → aplicar).",
    )
    sub = parser.add_subparsers(dest="comando", metavar="{mapear,extrair,aplicar}")
    _registrar_mapear(sub)
    _registrar_extrair(sub)
    _registrar_aplicar(sub)

    args = parser.parse_args(argv)

    if not args.comando:
        parser.print_help()
        return 1

    if args.comando == "mapear":
        res = mapear.mapear_repositorio(
            args.gitignore_path, args.output_path, args.linhas_config, args.excluir, args.copiar)
        return _exibir_mapear(res)

    if args.comando == "extrair":
        posicionais = [x for x in (args.resposta_ia, args.diretorio_projeto, args.output_path) if x is not None]
        if args.colar:
            if len(posicionais) != 2:
                parser.error("extrair --colar: informe apenas diretorio_projeto e output_path.")
            resposta_ia = None
            diretorio_projeto, output_path = posicionais
        else:
            if len(posicionais) != 3:
                parser.error("extrair: informe resposta_ia, diretorio_projeto e output_path "
                             "(ou use --colar com os 2 últimos).")
            resposta_ia, diretorio_projeto, output_path = posicionais
        res = extrator.executar_extracao(
            resposta_ia, diretorio_projeto, output_path,
            incluir_instrucoes=not args.sem_instrucoes, colar=args.colar, copiar=args.copiar)
        return _exibir_extrair(res)

    if args.comando == "aplicar":
        if args.instrucoes:
            print(aplicador.INSTRUCOES_IA)
            return 0
        posicionais = [x for x in (args.resposta_ia, args.diretorio_projeto) if x is not None]
        if args.colar:
            if len(posicionais) != 1:
                parser.error("aplicar --colar: informe apenas diretorio_projeto.")
            resposta_ia = None
            diretorio_projeto = posicionais[0]
        else:
            if len(posicionais) != 2:
                parser.error("aplicar: informe resposta_ia e diretorio_projeto "
                             "(ou use --colar com o diretório, ou --instrucoes).")
            resposta_ia, diretorio_projeto = posicionais
        res = aplicador.executar(
            resposta_ia, diretorio_projeto, args.aplicar, args.diff_path, args.sem_backup, args.colar)
        projeto_resolved = Path(diretorio_projeto).resolve()
        if res.sequenciado:
            return _rodar_sequenciado(res, projeto_resolved, args)
        return _exibir_aplicar(res, projeto_resolved, args.html_diff)

    return 1


def _confirmador_terminal(lote: bool, todos_comandos):
    """Devolve um confirmador callable(PassoComando)->bool que pergunta no terminal.

    Segurança: se o stdin NÃO é interativo (pipe/redirecionamento/automação), NÃO há
    como perguntar — o confirmador RECUSA tudo (retorna False), e a sequência para. Um
    comando nunca roda sem um 'sim' humano explícito.

    Modo lote: mostra todos os comandos de uma vez e pede um único 'sim'; a decisão é
    memorizada e reusada para cada chamada. Modo um-a-um: pergunta antes de cada comando.
    """
    import sys as _sys

    interativo = _sys.stdin.isatty()

    if not interativo:
        def _recusa(_pc):
            return False
        return _recusa

    if lote:
        print("\n\033[1;33m⚠️  Este plano executará os seguintes comando(s) na sua máquina:\033[0m")
        for i, pc in enumerate(todos_comandos):
            desc = f"  — {pc.descricao}" if pc.descricao else ""
            print(f"  [{i}] {pc.comando}{desc}")
        resp = input("\033[1mAutorizar TODOS os comandos acima? [s/N] \033[0m").strip().lower()
        aprovado_lote = resp in ("s", "sim", "y", "yes")

        def _confirma_lote(_pc):
            return aprovado_lote
        return _confirma_lote

    def _confirma_um(pc):
        desc = f"\n   {pc.descricao}" if pc.descricao else ""
        gates = []
        if pc.espera_exit is not None:
            gates.append(f"exit=={pc.espera_exit}")
        if pc.espera_conter is not None:
            gates.append(f"contém {pc.espera_conter!r}")
        info_gate = f"   (gate: {', '.join(gates)})\n" if gates else ""
        print(f"\n\033[1;33m▶ Comando:\033[0m {pc.comando}{desc}")
        if info_gate:
            print(info_gate, end="")
        resp = input("\033[1mExecutar este comando? [s/N] \033[0m").strip().lower()
        return resp in ("s", "sim", "y", "yes")
    return _confirma_um


def _exibir_sequenciado(res, projeto_path, parou_em) -> int:
    """Renderiza o resultado de uma execução sequenciada (modo C): diffs, saída dos
    comandos e o relatório de parada. Também imprime um bloco pronto para colar no chat."""
    print(f"📂 Projeto: {projeto_path}")
    print("\033[1;35m🔗 MODO SEQUENCIADO (edições + comandos)\033[0m\n")

    gravados = []
    for passo in res.passos:
        if passo.tipo == "edicao":
            arq = next((a for a in res.arquivos if a.caminho == passo.caminho), None)
            marca = ""
            if arq and arq.diff:
                add, rem = arq.adicionadas, arq.removidas
                marca = f" (\033[32m+{add}\033[0m/\033[31m−{rem}\033[0m)"
            print(f"\033[1;34m📝 [{passo.ordem}] edição: {passo.caminho}\033[0m{marca}")
            gravados.append(passo.caminho)
        else:
            pc = passo.comando
            rc = passo.resultado_comando
            print(f"\033[1;36m▶ [{passo.ordem}] comando: {pc.comando}\033[0m")
            if not rc.executado:
                motivo = rc.motivo_divergencia or "não executado"
                print(f"   \033[33m⏭️  {motivo}\033[0m")
                continue
            cor = "\033[31m" if rc.divergiu else "\033[32m"
            estado = "DIVERGIU" if rc.divergiu else "ok"
            ec = "timeout" if rc.expirou else f"exit {rc.exit_code}"
            print(f"   {cor}{estado}\033[0m ({ec})")
            if rc.stdout.strip():
                print("   \033[2mstdout:\033[0m")
                for ln in rc.stdout.rstrip().splitlines():
                    print(f"     {ln}")
            if rc.stderr.strip():
                print("   \033[2mstderr:\033[0m")
                for ln in rc.stderr.rstrip().splitlines():
                    print(f"     {ln}")
            if rc.divergiu:
                print(f"   \033[31m⛔ {rc.motivo_divergencia}\033[0m")

    print()
    if parou_em is not None:
        print(f"\033[1;31m⛔ Sequência interrompida no passo {parou_em}. "
              f"Passos seguintes NÃO foram executados.\033[0m")
    else:
        print("\033[1;32m✅ Sequência concluída.\033[0m")
    if gravados:
        print(f"\033[32m💾 Arquivos gravados: {', '.join(gravados)}\033[0m")

    # Bloco pronto para colar de volta no chat com a IA.
    print("\n\033[2m--- resumo para colar no chat ---\033[0m")
    linhas = []
    for passo in res.passos:
        if passo.tipo != "comando":
            continue
        rc = passo.resultado_comando
        if not rc.executado:
            linhas.append(f"$ {passo.comando.comando}\n[não executado: {rc.motivo_divergencia}]")
            continue
        ec = "timeout" if rc.expirou else f"exit {rc.exit_code}"
        corpo = (rc.stdout + rc.stderr).rstrip()
        linhas.append(f"$ {passo.comando.comando}  ({ec})\n{corpo}")
    print("\n\n".join(linhas) if linhas else "(nenhum comando executado)")

    return 1 if parou_em is not None else 0


def _rodar_sequenciado(res, projeto_path, args) -> int:
    """Orquestra a execução sequenciada (modo C) na CLI: opt-in, confirmação, execução.

    O core (aplicador.executar) já preparou `res` (passos + estados_finais). Aqui a UI:
    checa o opt-in (--permitir-comandos); mostra o AMBIENTE de execução (venv do
    projeto-alvo, se houver); monta o confirmador de terminal; chama o executor
    (única parte que grava e roda); e renderiza. Sem --permitir-comandos, o plano
    é recusado sem tocar nada.
    """
    if not args.permitir_comandos:
        print("\033[1;31m⛔ Este plano contém comando(s) a executar.\033[0m")
        print("   Para rodá-lo, use \033[1m--permitir-comandos\033[0m — ciente de que os "
              "comandos rodam na SUA máquina, com confirmação por comando.")
        print("   Comandos no plano:")
        for passo in res.passos:
            if passo.tipo == "comando":
                desc = f" — {passo.comando.descricao}" if passo.comando.descricao else ""
                print(f"     • {passo.comando.comando}{desc}")
        return 1

    _env, rotulo_ambiente = executor_sequencia.montar_ambiente(projeto_path)
    print(f"\033[36m🐍 Ambiente de execução: {rotulo_ambiente}\033[0m")

    comandos = [p.comando for p in res.passos if p.tipo == "comando"]
    confirmador = _confirmador_terminal(args.confirmar_lote, comandos)

    passos, parou_em = executor_sequencia.executar_sequencia(
        res.passos, projeto_path, confirmador, res.estados_finais,
        timeout_padrao=args.timeout_comando, sem_backup=args.sem_backup)

    return _exibir_sequenciado(res, projeto_path, parou_em)


if __name__ == "__main__":
    sys.exit(main())
