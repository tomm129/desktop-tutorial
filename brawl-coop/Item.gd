extends Area2D
# Item caído no chão. O jogador pega passando por cima; some sozinho depois
# de um tempo para não entulhar a arena.
# Ícones: pacote Generic Items do Kenney (CC0) — ver arte/LEIA-ME.md.

const RAIO := 22.0
const TEMPO_DE_VIDA := 15.0
const TAMANHO_NA_TELA := 34.0   # o ícone é redimensionado para caber nisso
const ALTURA_DO_BALANCO := 4.0  # sobe e desce parado no chão

var tipo := "kit"               # kit | frasco | pilhas
# Numa partida em rede quem manda nos itens e o anfitriao, igual aos
# inimigos: o cliente so mostra, e pede para pegar.
var remoto := false
var id_rede := 0

var _sprite: Sprite2D
var _tempo := 0.0

func _ready() -> void:
	var forma := CircleShape2D.new()
	forma.radius = RAIO
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

	# Zera antes de configurar (a Godot liga o bit 1 sozinha nos dois campos).
	collision_layer = 0
	collision_mask = 0
	set_collision_layer_value(4, true)   # camada 4 = itens no chão
	set_collision_mask_value(1, true)    # só o jogador encosta

	_sprite = Sprite2D.new()
	_sprite.texture = load("res://arte/itens2/%s.png" % tipo)
	# Cada ícone tem um tamanho diferente: normaliza pelo lado maior.
	var t := _sprite.texture.get_size()
	_sprite.scale = Vector2.ONE * (TAMANHO_NA_TELA / max(t.x, t.y))
	add_child(_sprite)

	body_entered.connect(_ao_encostar)
	add_to_group("itens")

func _process(delta: float) -> void:
	_tempo += delta
	_sprite.position.y = sin(_tempo * 3.0) * ALTURA_DO_BALANCO - 8.0
	# Pisca no fim da vida, avisando que vai sumir.
	if _tempo > TEMPO_DE_VIDA - 3.0:
		_sprite.visible = fmod(_tempo, 0.3) > 0.15
	if _tempo >= TEMPO_DE_VIDA:
		queue_free()
	queue_redraw()

func _ao_encostar(corpo: Node2D) -> void:
	if not corpo.has_method("pegar_item"):
		return
	if corpo.por_ia:
		return   # aliado de computador nao cata item, deixa para a gente
	var principal := get_tree().get_first_node_in_group("main")

	# Cliente: nao pega por conta, pede ao anfitriao. Senao duas pessoas
	# pegariam o mesmo item, cada uma na sua tela.
	if remoto:
		if not corpo.remoto and principal != null:
			principal.pede_pegar_item(id_rede)
		return

	# Anfitriao (ou jogo local). Se quem encostou e de outra maquina, o item
	# vai para o inventario DELA.
	if corpo.remoto:
		if principal != null:
			principal.entrega_item(corpo.id_de_rede, tipo)
			queue_free()
		return
	if corpo.pegar_item(tipo):
		queue_free()

func _draw() -> void:
	# Piscando (fim da vida): esconde a sombra junto com o ícone, senão fica
	# uma sombra preta sozinha na grama.
	if not _sprite.visible:
		return

	# Sombrinha no chão, para o ícone não parecer colado na tela
	draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.4))
	draw_circle(Vector2.ZERO, 13.0, Color(0, 0, 0, 0.3))
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
