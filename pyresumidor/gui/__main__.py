"""Ponto de entrada da GUI:  python -m pyresumidor.gui

PySide6 é dependência opcional (grupo [gui] do pyproject). Este é o ÚNICO módulo
do projeto que a importa — o core e a CLI permanecem sem ela.
"""
import sys


def main() -> int:
    try:
        from pyresumidor.gui.app import iniciar
    except ImportError as e:
        print("❌ A GUI exige PySide6. Instale com:")
        print('   pip install -e ".[gui]"')
        print(f"   (detalhe: {e})")
        return 1
    return iniciar()


if __name__ == "__main__":
    sys.exit(main())
