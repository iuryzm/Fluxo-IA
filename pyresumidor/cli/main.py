"""Ponto de entrada único do toolkit: despacha para mapear / extrair / aplicar.

Em vez de lembrar três comandos diferentes, use:
    python main.py mapear     ...   (mapear.py)
    python main.py extrair  ...   (extrator.py)
    python main.py aplicar  ...   (aplicador.py)

Cada subcomando aceita exatamente os mesmos argumentos do script original e apenas
delega para a função `executar*` que cada módulo já expõe — nenhuma lógica é duplicada
aqui.
"""

import argparse
import sys

from pyresumidor.core import mapear, extrator, aplicador


def _registrar_mapear(sub):
    """Registra, valida e define todos os argumentos da interface de comandos voltados à operação 'mapear'."""
    p = sub.add_parser(
        "mapear",
        help="Gera o mapear de arquitetura do projeto (mapear.py).",
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
    p.add_argument(
        "--copiar",
        action="store_true",
        help="Também copia o mapear para a área de transferência (pronto p/ colar no chat).",
    )
    return p


def _registrar_extrair(sub):
    """Registra, valida e define todos os argumentos da interface de comandos voltados à operação 'extrair'."""
    p = sub.add_parser(
        "extrair",
        help="Extrai os trechos de código pedidos pela IA (extrator.py).",
        description="Extrai código-fonte baseado em um JSON da IA.",
    )
    p.add_argument("resposta_ia", nargs="?", help="Arquivo txt/md com a resposta (JSON) da IA. Opcional com --colar.")
    p.add_argument("diretorio_projeto", nargs="?", help="Caminho raiz do projeto (ex: ../VisualizadorPN).")
    p.add_argument("output_path", nargs="?", help="Arquivo .md de saída com os códigos extraídos.")
    p.add_argument(
        "--sem-instrucoes",
        action="store_true",
        help="Não anexa ao fim da saída as instruções de formato do aplicador.py.",
    )
    p.add_argument(
        "--colar",
        action="store_true",
        help="Lê a resposta da IA da área de transferência (dispensa 'resposta_ia').",
    )
    p.add_argument(
        "--copiar",
        action="store_true",
        help="Copia a saída (código extraído) para a área de transferência.",
    )
    return p


def _registrar_aplicar(sub):
    """Registra, valida e define todos os argumentos da interface de comandos voltados à operação 'aplicar'."""
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
    p.add_argument(
        "--colar",
        action="store_true",
        help="Lê a resposta da IA da área de transferência (dispensa 'resposta_ia').",
    )
    p.add_argument(
        "--html-diff",
        nargs="?",
        const="",
        default=None,
        metavar="ARQUIVO.html",
        help="Gera uma página HTML com os diffs coloridos e abre no navegador "
             "(sem valor = arquivo temporário).",
    )
    p.add_argument("--instrucoes", action="store_true", help="Imprime as instruções para colar no chat com a IA e sai.")
    return p


def main(argv=None):
    """Ponto de entrada único e centralizado da CLI encarregado de rotear os argumentos e despachar os comandos."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Toolkit de edição de código assistida por IA (pipeline mapear → extrair → aplicar).",
    )
    sub = parser.add_subparsers(dest="comando", metavar="{mapear,extrair,aplicar}")

    _registrar_mapear(sub)
    _registrar_extrair(sub)
    p_aplicar = _registrar_aplicar(sub)

    args = parser.parse_args(argv)

    if not args.comando:
        parser.print_help()
        sys.exit(1)

    if args.comando == "mapear":
        mapear.mapear_repositorio(
            args.gitignore_path, args.output_path, args.linhas_config, args.excluir, args.copiar
        )

    elif args.comando == "extrair":
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
        extrator.executar_extracao(
            resposta_ia,
            diretorio_projeto,
            output_path,
            incluir_instrucoes=not args.sem_instrucoes,
            colar=args.colar,
            copiar=args.copiar,
        )

    elif args.comando == "aplicar":
        if args.instrucoes:
            print(aplicador.INSTRUCOES_IA)
            return
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
        aplicador.executar(
            resposta_ia,
            diretorio_projeto,
            args.aplicar,
            args.diff_path,
            args.sem_backup,
            args.html_diff,
            args.colar,
        )


if __name__ == "__main__":
    main()

# Como usar
# python .\main.py mapear ..\VisualizadorPN\.gitignore .\test\mapear_out.md --linhas-config 10 --excluir README.md RELEASE_PROCESS.md AI_orientation.txt AUTHORS.md scripts/* 
# python .\main.py extrair .\test\extrator_in.json ..\VisualizadorPN .\test\extrator_out.md
# python .\main.py aplicar .\test\aplicador_in.md ..\VisualizadorPN --html-diff .\test\aplicador_out.html
# python .\main.py aplicar .\test\aplicador_in.md ..\VisualizadorPN --html-diff .\test\aplicador_out.html --aplicar
# python main.py mapear    ..\VisualizadorPN\.gitignore .\test\resumo.md --linhas-config 10 --excluir *.env
# python main.py extrair .\test\resposta.json ..\VisualizadorPN .\test\codigo_para_ia.md
# python main.py aplicar .\test\resposta.md  ..\VisualizadorPN --aplicar
# python main.py aplicar --instrucoes
