"""Fixtures compartilhadas: monta projetos-exemplo descartáveis em tmp_path."""
import textwrap
import pytest


@pytest.fixture
def projeto(tmp_path):
    """Cria um projeto mínimo com .gitignore (allowlist) e um módulo .py.

    Devolve o Path da raiz do projeto temporário. Cada teste recebe um diretório
    novo e isolado — nada vaza entre testes nem toca o repo real.
    """
    raiz = tmp_path

    # .gitignore no mesmo estilo allowlist do projeto real
    (raiz / ".gitignore").write_text(
        "*\n!.gitignore\n!exemplo.py\n!config.yaml\n",
        encoding="utf-8",
    )

    # Módulo Python com classe, método decorado e função de nível de módulo.
    # O decorador @prop_falsa existe para travar a regressão de preservação
    # de decorador (ast.get_source_segment os descartava).
    (raiz / "exemplo.py").write_text(
        textwrap.dedent('''\
            """Modulo de exemplo para os testes."""


            def prop_falsa(fn):
                return fn


            def funcao_solta(x):
                """Funcao de nivel de modulo."""
                return x + 1


            class Motor:
                """Classe de exemplo."""

                @prop_falsa
                def run(self):
                    return "rodando"

                def reset(self):
                    return None


            class OutroMotor:
                def run(self):
                    return "outro"
        '''),
        encoding="utf-8",
    )

    (raiz / "config.yaml").write_text("chave: valor\n", encoding="utf-8")

    return raiz


@pytest.fixture
def gitignore(projeto):
    """Caminho do .gitignore do projeto-exemplo (entrada de mapear_repositorio)."""
    return projeto / ".gitignore"
