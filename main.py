"""Ponto de entrada único do toolkit: despacha para mapa / extrair / aplicar.

Em vez de lembrar três comandos diferentes, use:
    python main.py mapa     ...   (gerar_mapa.py)
    python main.py extrair  ...   (extrator.py)
    python main.py aplicar  ...   (aplicador.py)

Cada subcomando aceita exatamente os mesmos argumentos do script original e apenas
delega para a função `executar*` que cada módulo já expõe — nenhuma lógica é duplicada
aqui.
"""

import argparse
import sys

import gerar_mapa
import extrator
import aplicador


def _registrar_mapa(sub):
    p = sub.add_parser(
        "mapa",
        help="Gera o mapa de arquitetura do projeto (gerar_mapa.py).",
        description="Gera um resumo do código Python baseado no .gitignore.",
    )
    p.add_argument("gitignore_path", help="Caminho para o .gitignore do projeto alvo.")
    p.add_argument("output_path", help="Caminho e nome do arquivo .md de saída.")
    p.add_argument(
        "--linhas-config",
        type=int,
        default=20,
        help="Nº de linhas de prévia para arquivos de config/outros. 0 = sem prévia (default: 20).",
    )
    p.add_argument(
        "--excluir",
        nargs="*",
        default=[],
        metavar="PADRAO",
        help="Padrões glob de arquivos a NÃO incluir no resumo (soma-se ao .resumoignore).",
    )
    return p


def _registrar_extrair(sub):
    p = sub.add_parser(
        "extrair",
        help="Extrai os trechos de código pedidos pela IA (extrator.py).",
        description="Extrai código-fonte baseado em um JSON da IA.",
    )
    p.add_argument("resposta_ia", help="Arquivo txt/md com a resposta (JSON) da IA.")
    p.add_argument("diretorio_projeto", help="Caminho raiz do projeto (ex: ../VisualizadorPN).")
    p.add_argument("output_path", help="Arquivo .md de saída com os códigos extraídos.")
    p.add_argument(
        "--sem-instrucoes",
        action="store_true",
        help="Não anexa ao fim da saída as instruções de formato do aplicador.py.",
    )
    return p


def _registrar_aplicar(sub):
    p = sub.add_parser(
        "aplicar",
        help="Aplica as alterações propostas pela IA (aplicador.py).",
        description="Aplica alterações da IA por nome via AST (e edições por âncora).",
    )
    p.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta da IA (plano + blocos).")
    p.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto (ex: ../VisualizadorPN).")
    p.add_argument("--aplicar", action="store_true", help="Grava as alterações (default: dry-run).")
    p.add_argument("--diff", dest="diff_path", default=None, help="Salva o patch unificado combinado neste caminho.")
    p.add_argument("--sem-backup", action="store_true", help="Não cria arquivos .bak ao gravar.")
    p.add_argument("--instrucoes", action="store_true", help="Imprime as instruções para colar no chat com a IA e sai.")
    return p


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Toolkit de edição de código assistida por IA (pipeline mapa → extrair → aplicar).",
    )
    sub = parser.add_subparsers(dest="comando", metavar="{mapa,extrair,aplicar}")

    _registrar_mapa(sub)
    _registrar_extrair(sub)
    p_aplicar = _registrar_aplicar(sub)

    args = parser.parse_args(argv)

    if not args.comando:
        parser.print_help()
        sys.exit(1)

    if args.comando == "mapa":
        gerar_mapa.gerar_mapa_repositorio(
            args.gitignore_path, args.output_path, args.linhas_config, args.excluir
        )

    elif args.comando == "extrair":
        extrator.executar_extracao(
            args.resposta_ia,
            args.diretorio_projeto,
            args.output_path,
            incluir_instrucoes=not args.sem_instrucoes,
        )

    elif args.comando == "aplicar":
        if args.instrucoes:
            print(aplicador.INSTRUCOES_IA)
            return
        if not args.resposta_ia or not args.diretorio_projeto:
            p_aplicar.error("são necessários 'resposta_ia' e 'diretorio_projeto' (ou use --instrucoes).")
        aplicador.executar(
            args.resposta_ia,
            args.diretorio_projeto,
            args.aplicar,
            args.diff_path,
            args.sem_backup,
        )


if __name__ == "__main__":
    main()

# Como usar
# python main.py mapa    ..\VisualizadorPN\.gitignore .\test\resumo.md --linhas-config 10 --excluir *.env
# python main.py extrair .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md
# python main.py aplicar .\test\resposta.md  ..\VisualizadorPN --aplicar
# python main.py aplicar --instrucoes