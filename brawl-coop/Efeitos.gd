extends Node
# Efeitos de impacto (autoload). É o que dá "peso" às pancadas sem precisar de
# quadro de animação novo: faísca, número de dano subindo e tremor de tela.
#
# Por que isto existe: a arte dos personagens não tem quadro de ataque, de dano
# nem de morte. Sem esses quadros, quem comunica que alguém bateu ou apanhou é
# o efeito em volta — e é aí que dá para melhorar muito com pouco.

const COR_DE_DANO := Color(1.0, 0.85, 0.25)
const COR_DE_CURA := Color(0.45, 1.0, 0.55)

# --- Faíscas ----------------------------------------------------------------

# Estouro rápido de partículas no ponto do impacto.
func faisca(pai: Node, onde: Vector2, cor: Color, quantas := 12, forca := 150.0) -> void:
	if pai == null or not is_instance_valid(pai):
		return
	var p := CPUParticles2D.new()
	p.amount = quantas
	p.one_shot = true
	p.explosiveness = 1.0
	p.lifetime = 0.4
	p.direction = Vector2.UP
	p.spread = 180.0
	p.gravity = Vector2(0, 420)
	p.initial_velocity_min = forca * 0.4
	p.initial_velocity_max = forca
	p.scale_amount_min = 1.5
	p.scale_amount_max = 3.5
	p.color = cor
	p.global_position = onde
	p.emitting = true
	pai.add_child(p)
	_apaga_depois(p, 1.2)

# Poeira no chão, para pulos e investidas.
func poeira(pai: Node, onde: Vector2) -> void:
	if pai == null or not is_instance_valid(pai):
		return
	var p := CPUParticles2D.new()
	p.amount = 8
	p.one_shot = true
	p.explosiveness = 0.9
	p.lifetime = 0.5
	p.direction = Vector2.UP
	p.spread = 60.0
	p.gravity = Vector2(0, -20)
	p.initial_velocity_min = 10.0
	p.initial_velocity_max = 40.0
	p.scale_amount_min = 2.0
	p.scale_amount_max = 5.0
	p.color = Color(0.75, 0.7, 0.55, 0.55)
	p.global_position = onde
	p.emitting = true
	pai.add_child(p)
	_apaga_depois(p, 1.2)

# --- Número de dano ---------------------------------------------------------

func numero(pai: Node, onde: Vector2, valor: int, cor := COR_DE_DANO) -> void:
	if pai == null or not is_instance_valid(pai) or valor <= 0:
		return
	var n := NumeroFlutuante.new()
	n.texto = str(valor)
	n.cor = cor
	n.global_position = onde + Vector2(randf_range(-8.0, 8.0), 0.0)
	pai.add_child(n)

func numero_de_cura(pai: Node, onde: Vector2, valor: int) -> void:
	numero(pai, onde, valor, COR_DE_CURA)

# Número que sobe e some. Fica aqui dentro porque só serve para isto.
class NumeroFlutuante extends Node2D:
	const SUBIDA := 46.0
	const DURACAO := 0.8

	var texto := "0"
	var cor := Color.WHITE
	var _tempo := 0.0

	func _process(delta: float) -> void:
		_tempo += delta
		# Sobe rápido no começo e desacelera, que é o que dá a sensação de
		# "saltou" em vez de "deslizou".
		var quanto: float = min(_tempo / DURACAO, 1.0)
		position.y = -SUBIDA * (1.0 - pow(1.0 - quanto, 2.0))
		queue_redraw()
		if _tempo >= DURACAO:
			queue_free()

	func _draw() -> void:
		var fonte := ThemeDB.fallback_font
		var tamanho := 20
		var alfa: float = 1.0 - pow(_tempo / DURACAO, 3.0)
		var largura := fonte.get_string_size(texto, HORIZONTAL_ALIGNMENT_LEFT, -1, tamanho).x
		# Contorno preto: sobre grama clara, número amarelo puro some.
		for desvio in [Vector2(1, 1), Vector2(-1, 1), Vector2(1, -1), Vector2(-1, -1)]:
			draw_string(fonte, Vector2(-largura / 2.0, 0) + desvio, texto,
				HORIZONTAL_ALIGNMENT_LEFT, -1, tamanho, Color(0, 0, 0, alfa * 0.8))
		draw_string(fonte, Vector2(-largura / 2.0, 0), texto,
			HORIZONTAL_ALIGNMENT_LEFT, -1, tamanho, Color(cor.r, cor.g, cor.b, alfa))

# --- Apoio ------------------------------------------------------------------

func _apaga_depois(no: Node, segundos: float) -> void:
	var relogio := get_tree().create_timer(segundos)
	relogio.timeout.connect(func():
		if is_instance_valid(no):
			no.queue_free())
