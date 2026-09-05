extends Area2D
# Projétil. Quem configura é a classe que atirou (Personagem._dispara): dano,
# cor, alcance e, se for o caso, estouro em área (mago) ou lentidão (druida).

const VELOCIDADE := 750.0
const RAIO := 6.0
const TEMPO_DO_ESTOURO := 0.22   # quanto tempo o círculo do estouro fica na tela

var direcao := Vector2.RIGHT
var dano := 25
var cor := Color(1.0, 0.85, 0.2)
var alcance := 450.0             # distância até sumir sozinha
var raio_estouro := 0.0          # > 0 = explode ao acertar
var dano_estouro := 0
var lentidao := 0.0              # > 0 = deixa o alvo lento (0.45 = 45% mais devagar)
var tempo_lentidao := 0.0

var _percorrido := 0.0
var _tempo_estouro := 0.0        # > 0 = já acertou, está só mostrando o estouro

func _ready() -> void:
	var forma := CircleShape2D.new()
	forma.radius = RAIO
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

	# Zera antes de configurar (a Godot liga o bit 1 sozinha nos dois campos).
	collision_layer = 0
	collision_mask = 0
	set_collision_layer_value(3, true)   # camada 3 = tiros da party
	set_collision_mask_value(2, true)    # máscara 2 = só enxerga inimigos
	body_entered.connect(_ao_acertar)

func _process(delta: float) -> void:
	# Já acertou: fica parada só o tempo de desenhar o estouro.
	if _tempo_estouro > 0.0:
		_tempo_estouro -= delta
		queue_redraw()
		if _tempo_estouro <= 0.0:
			queue_free()
		return

	var passo := VELOCIDADE * delta
	global_position += direcao * passo
	_percorrido += passo
	if _percorrido >= alcance:
		queue_free()

func _ao_acertar(corpo: Node2D) -> void:
	if _tempo_estouro > 0.0:
		return   # não acerta duas vezes durante o estouro
	if corpo.has_method("receber_dano"):
		corpo.receber_dano(dano)
		if lentidao > 0.0 and corpo.has_method("aplicar_lentidao"):
			corpo.aplicar_lentidao(lentidao, tempo_lentidao)

	if raio_estouro > 0.0:
		for inimigo in get_tree().get_nodes_in_group("inimigos"):
			if inimigo != corpo and global_position.distance_to(inimigo.global_position) <= raio_estouro:
				inimigo.receber_dano(dano_estouro)
		# Some de vista, mas continua vivo até o desenho do estouro acabar.
		set_deferred("monitoring", false)
		_tempo_estouro = TEMPO_DO_ESTOURO
		return

	queue_free()

func _draw() -> void:
	if _tempo_estouro > 0.0:
		var quanto := 1.0 - (_tempo_estouro / TEMPO_DO_ESTOURO)
		draw_circle(Vector2.ZERO, raio_estouro * quanto, Color(cor.r, cor.g, cor.b, 0.35 * (1.0 - quanto)))
		draw_arc(Vector2.ZERO, raio_estouro * quanto, 0.0, TAU, 32,
			Color(cor.r, cor.g, cor.b, 1.0 - quanto), 4.0)
		return
	draw_circle(Vector2.ZERO, RAIO, cor)
	draw_circle(Vector2.ZERO, RAIO * 0.5, Color(1, 1, 1, 0.8))
