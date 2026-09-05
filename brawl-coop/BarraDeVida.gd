extends RefCounted
class_name BarraDeVida
# Barra de vida "overhead" (aquela que fica em cima da cabeça).
#
# É desenhada por código, não é imagem: assim a mesma função serve para a party
# e para os inimigos, em qualquer largura, sem precisar de um PNG por estado.
#
# A cor NÃO é a da classe — é a da vida, em faixas, igual ao exemplo:
#   100% verde | 80% verde-claro | 60% amarelo | 40% laranja | 20% vermelho | 0% cinza
# (com a cor da classe, um guerreiro cheio tinha barra vermelha e parecia
# estar morrendo)
#
# Uso, de dentro de um _draw():
#   BarraDeVida.desenha(self, Vector2(0, -76), 52.0, vida, vida_maxima, true)

const ALTURA := 8.0
const CONTORNO := 2.0
const VAO_DO_CORACAO := 5.0
const PIXEL_DO_CORACAO := 2.0
const AVISO_ABAIXO_DE := 0.25   # daqui para baixo a barra pulsa

# Coração em "pixel art", 7 x 6. Cada '#' vira um quadradinho.
const CORACAO := [
	".##.##.",
	"#######",
	"#######",
	".#####.",
	"..###..",
	"...#...",
]

# As faixas do exemplo: (vida mínima da faixa, cor)
const FAIXAS := [
	[0.80, Color(0.16, 0.85, 0.18)],   # verde
	[0.60, Color(0.45, 0.82, 0.16)],   # verde-limão
	[0.40, Color(0.88, 0.85, 0.15)],   # amarelo
	[0.20, Color(0.95, 0.55, 0.10)],   # laranja
	[0.001, Color(0.70, 0.10, 0.18)],  # vermelho
]
const COR_VAZIA := Color(0.42, 0.42, 0.45)
const COR_FUNDO := Color(0.16, 0.16, 0.19)
const COR_CONTORNO := Color(0.05, 0.05, 0.07)

# Tamanho total do conjunto (barra + vao + coracao + riscos). Quem empilha as
# barras precisa disso para saber se duas se encostam.
static func tamanho(largura: float, com_coracao: bool, riscos: int) -> Vector2:
	var larg := largura + CONTORNO * 2.0
	if com_coracao:
		larg += VAO_DO_CORACAO + CORACAO[0].length() * PIXEL_DO_CORACAO
	var alt := ALTURA + CONTORNO * 2.0 + riscos * 3.0
	return Vector2(larg, alt)

# Retangulo que a barra inteira ocupa (com contorno, coracao e riscos), dado o
# centro da BARRA. E o que o empilhamento usa para saber se duas se encostam --
# vem daqui de proposito, para nao descolar do desenho.
static func caixa(meio: Vector2, largura: float, com_coracao: bool, riscos: int) -> Rect2:
	var tam := tamanho(largura, com_coracao, riscos)
	return Rect2(Vector2(meio.x - largura / 2.0 - CONTORNO, meio.y - CONTORNO), tam)

static func cor_da_vida(fracao: float) -> Color:
	for faixa in FAIXAS:
		if fracao >= faixa[0]:
			return faixa[1]
	return COR_VAZIA

# ci  = quem vai desenhar (o próprio personagem, de dentro do _draw)
# meio = centro da barra, em coordenadas locais
# cor_extra    = risco fino embaixo da barra (usamos a cor da CLASSE, que e o
#                que diz quem e quem quando os dois membros aparecem juntos)
# marca_aliado = risco branco no fim, marcando o membro controlado pela IA
static func desenha(ci: CanvasItem, meio: Vector2, largura: float,
		vida: int, vida_maxima: int, com_coracao: bool,
		cor_extra := Color(0, 0, 0, 0), marca_aliado := false) -> void:
	var fracao := clampf(float(vida) / float(max(vida_maxima, 1)), 0.0, 1.0)
	var cor := cor_da_vida(fracao)

	# Vida baixa: a barra inteira pulsa, para chamar a atenção sem precisar de
	# um efeito separado.
	var pulso := 1.0
	if fracao > 0.0 and fracao <= AVISO_ABAIXO_DE:
		var t := Time.get_ticks_msec() / 1000.0
		pulso = 0.75 + 0.25 * sin(t * 9.0)

	# Quem fica centrado no personagem e a BARRA, nao o conjunto: o coracao
	# sobra para a direita. Centrando o conjunto, a barra ficava deslocada
	# para a esquerda do boneco, porque o coracao so ocupa um lado.
	var x0 := meio.x - largura / 2.0
	var y0 := meio.y

	# Contorno + fundo
	ci.draw_rect(Rect2(Vector2(x0 - CONTORNO, y0 - CONTORNO),
		Vector2(largura + CONTORNO * 2.0, ALTURA + CONTORNO * 2.0)), COR_CONTORNO)
	ci.draw_rect(Rect2(Vector2(x0, y0), Vector2(largura, ALTURA)), COR_FUNDO)

	# Trilho vazio (cinza) e, por cima, o quanto ainda tem de vida
	ci.draw_rect(Rect2(Vector2(x0, y0), Vector2(largura, ALTURA)), COR_VAZIA)
	if fracao > 0.0:
		var c := Color(cor.r, cor.g, cor.b, pulso)
		ci.draw_rect(Rect2(Vector2(x0, y0), Vector2(largura * fracao, ALTURA)), c)
		# Brilho fino no topo, o que dá o ar de barra "de jogo" e não de retângulo
		ci.draw_rect(Rect2(Vector2(x0, y0), Vector2(largura * fracao, 2.0)),
			Color(1, 1, 1, 0.28 * pulso))

	if com_coracao:
		var canto := Vector2(x0 + largura + VAO_DO_CORACAO, y0 - 2.0)
		_desenha_coracao(ci, canto, cor if fracao > 0.0 else COR_VAZIA, pulso)

	# Riscos de identidade, alinhados com a barra (nao com o personagem, senao
	# ficariam tortos por causa do coracao, que so existe de um lado).
	var y_risco := y0 + ALTURA + CONTORNO
	if cor_extra.a > 0.0:
		ci.draw_rect(Rect2(Vector2(x0, y_risco), Vector2(largura, 3.0)), cor_extra)
		y_risco += 3.0
	if marca_aliado:
		ci.draw_rect(Rect2(Vector2(x0, y_risco), Vector2(largura, 2.0)), Color(1, 1, 1, 0.55))

static func _desenha_coracao(ci: CanvasItem, canto: Vector2, cor: Color, pulso: float) -> void:
	var p := PIXEL_DO_CORACAO
	# Sombra do coração (1px deslocado), para ele não sumir no fundo claro
	for linha in CORACAO.size():
		for coluna in CORACAO[linha].length():
			if CORACAO[linha][coluna] != "#":
				continue
			var pos := canto + Vector2(coluna * p, linha * p)
			ci.draw_rect(Rect2(pos + Vector2(1, 1), Vector2(p, p)), Color(0, 0, 0, 0.55))
	for linha in CORACAO.size():
		for coluna in CORACAO[linha].length():
			if CORACAO[linha][coluna] != "#":
				continue
			var pos := canto + Vector2(coluna * p, linha * p)
			ci.draw_rect(Rect2(pos, Vector2(p, p)), Color(cor.r, cor.g, cor.b, pulso))
