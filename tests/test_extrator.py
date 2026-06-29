"""Testes de extrator: regressao de decorador, notacao Classe.metodo, erro-como-dado."""
from pyresumidor.core import extrator


def test_extrair_arquivo_completo(projeto, tmp_path):
    entrada = tmp_path / "req.json"
    entrada.write_text('{"arquivos_completos": ["exemplo.py"], "classes": {}, "funcoes": {}}',
                       encoding="utf-8")
    saida = tmp_path / "out.md"
    res = extrator.executar_extracao(str(entrada), str(projeto), str(saida), incluir_instrucoes=False)
    assert res.sucesso is True
    assert len(res.itens) == 1
    assert res.itens[0].encontrado is True
    assert res.itens[0].tipo == "arquivo"


def test_extrair_preserva_decorador(projeto, tmp_path):
    # Regressao: @prop_falsa NAO pode sumir do codigo extraido de Motor.run
    entrada = tmp_path / "req.json"
    entrada.write_text('{"arquivos_completos": [], "classes": {}, '
                       '"funcoes": {"exemplo.py": ["Motor.run"]}}', encoding="utf-8")
    saida = tmp_path / "out.md"
    res = extrator.executar_extracao(str(entrada), str(projeto), str(saida), incluir_instrucoes=False)
    assert res.sucesso is True
    assert "@prop_falsa" in res.conteudo
    assert "def run" in res.conteudo


def test_extrair_classe_metodo_desambigua(projeto, tmp_path):
    # Motor.run e OutroMotor.run coexistem; a notacao pontilhada deve pegar so o de Motor
    entrada = tmp_path / "req.json"
    entrada.write_text('{"arquivos_completos": [], "classes": {}, '
                       '"funcoes": {"exemplo.py": ["Motor.run"]}}', encoding="utf-8")
    saida = tmp_path / "out.md"
    res = extrator.executar_extracao(str(entrada), str(projeto), str(saida), incluir_instrucoes=False)
    # "rodando" e do Motor.run; "outro" e do OutroMotor.run e NAO deve aparecer
    assert "rodando" in res.conteudo
    assert "outro" not in res.conteudo


def test_extrair_arquivo_inexistente_marca_nao_encontrado(projeto, tmp_path):
    entrada = tmp_path / "req.json"
    entrada.write_text('{"arquivos_completos": ["nao_existe.py"], "classes": {}, "funcoes": {}}',
                       encoding="utf-8")
    saida = tmp_path / "out.md"
    res = extrator.executar_extracao(str(entrada), str(projeto), str(saida), incluir_instrucoes=False)
    assert res.sucesso is True   # arquivo faltando nao anula a extracao
    assert res.itens[0].encontrado is False


def test_extrair_resposta_inexistente_vira_erro(projeto, tmp_path):
    saida = tmp_path / "out.md"
    res = extrator.executar_extracao(str(tmp_path / "fantasma.json"), str(projeto), str(saida))
    assert res.sucesso is False
    assert res.erros


def test_json_malformado_vira_erro_nao_systemexit(projeto, tmp_path):
    # Regressao: JSON invalido na resposta da IA deve virar ErroEntrada (capturada
    # como sucesso=False), NUNCA sys.exit/SystemExit — que na GUI derrubava a janela.
    entrada = tmp_path / "resp.md"
    entrada.write_text(
        '{"arquivos_completos": ["x.py"], "classes": {}, "funcoes": {},}',  # virgula sobrando
        encoding="utf-8")
    saida = tmp_path / "out.md"
    # se ainda houvesse sys.exit, isto levantaria SystemExit e o teste FALHARIA aqui
    res = extrator.executar_extracao(str(entrada), str(projeto), str(saida))
    assert res.sucesso is False
    assert res.erros
