"""Coloca a raiz do repo no sys.path para que `import pyresumidor` resolva
sem precisar de `pip install -e .`. Continua válido se você instalar depois.
"""
import sys
from pathlib import Path

raiz = Path(__file__).resolve().parent
if str(raiz) not in sys.path:
    sys.path.insert(0, str(raiz))
