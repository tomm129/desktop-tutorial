extends Node2D
# Camada que desenha TODAS as barras de vida da arena.
#
# Por que uma camada separada, em vez de cada um desenhar a sua:
#
# 1. ATRÁS DO PERSONAGEM. A arena usa y_sort, então quem está mais à frente
#    (mais embaixo na tela) desenha por cima de quem está atrás -- inclusive
#    por cima da BARRA de quem está atrás. Como este nó é irmão da arena e
#    entra DEPOIS dela, tudo o que ele desenha fica por cima de todo mundo.
#
# 2. UMA EM CIMA DA OUTRA. Com todas as barras sendo posicionadas no mesmo
#    lugar, dá para empilhar: se duas se encostam, a de quem está atrás sobe
#    até sobrar espaço.
#
# Quem informa o que desenhar são os próprios personagens, pelo método
# dados_da_barra().

const MARGEM_ENTRE_BARRAS := 3.0
const MAXIMO_DE_EMPURROES := 12   # trava de segurança contra laço infinito

func _process(_delta: float) -> void:
	queue_redraw()

# Junta o que cada personagem quer desenhar.
func _monta_pedidos() -> Array:
	var pedidos := []
	for grupo in ["jogador", "inimigos"]:
		for no in get_tree().get_nodes_in_group(grupo):
			if not no.has_method("dados_da_barra"):
				continue
			var d: Dictionary = no.dados_da_barra()
			if d.is_empty():
				continue   # este aqui não quer barra agora
			d["no"] = no
			pedidos.append(d)
	return pedidos

# Decide ONDE cada barra vai ficar, empurrando para cima o que se encostar.
# Separado do desenho de propósito: assim dá para testar o empilhamento sem
# precisar de tela, conferindo se sobrou alguma sobreposição.
func calcula() -> Array:
	var pedidos := _monta_pedidos()

	# Quem está mais à FRENTE (Y maior) fica com o lugar natural da sua barra;
	# quem está atrás é que sobe. Por isso a frente é colocada primeiro.
	pedidos.sort_custom(func(a, b): return a["no"].global_position.y > b["no"].global_position.y)

	var saida := []
	var ocupado := []
	for d in pedidos:
		var tam: Vector2 = BarraDeVida.tamanho(d["largura"], d["coracao"], d["riscos"])
		var meio: Vector2 = d["no"].global_position + Vector2(0, d["altura"])
		var caixa := BarraDeVida.caixa(meio, d["largura"], d["coracao"], d["riscos"])

		# Sobe enquanto estiver encostando em alguma barra já colocada.
		for tentativa in MAXIMO_DE_EMPURROES:
			var bateu := false
			for outra in ocupado:
				if caixa.intersects(outra):
					caixa.position.y = outra.position.y - tam.y - MARGEM_ENTRE_BARRAS
					bateu = true
					break
			if not bateu:
				break
		ocupado.append(caixa)
		saida.append({"d": d, "caixa": caixa, "meio": meio, "tam": tam})
	return saida

func _draw() -> void:
	for item in calcula():
		var d: Dictionary = item["d"]
		var caixa: Rect2 = item["caixa"]
		var meio: Vector2 = item["meio"]
		var tam: Vector2 = item["tam"]

		# caixa.position ja inclui o contorno; o desenho quer o centro da barra.
		var y_da_barra: float = caixa.position.y + BarraDeVida.CONTORNO
		BarraDeVida.desenha(self, Vector2(meio.x, y_da_barra), d["largura"],
			d["vida"], d["vida_maxima"], d["coracao"], d["cor_extra"], d["marca"])

		# Se a barra subiu, um risco liga ela ao dono -- senão fica solta no ar
		# e não dá para saber de quem é.
		var subiu: float = meio.y - (caixa.position.y + BarraDeVida.CONTORNO)
		if subiu > MARGEM_ENTRE_BARRAS + 1.0:
			draw_line(Vector2(meio.x, caixa.position.y + tam.y),
				Vector2(meio.x, meio.y + tam.y), Color(0, 0, 0, 0.4), 1.0)
