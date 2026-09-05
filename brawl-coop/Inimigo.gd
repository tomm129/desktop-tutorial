extends CharacterBody2D
# Inimigo (goblin): persegue o membro vivo da party mais perto e causa dano no
# contato. Pode ficar LENTO (tiro do druida) ou PRESO (raízes do druida).
# Ao morrer, cai, às vezes larga um item, e some devagar.
#
# MODO NEUTRO: com "neutro = true" ele continua andando e animando, mas NÃO
# causa dano. Serve para assistir o jogo rodando sem morrer. Quem liga e
# desliga é a Main, na tecla N.
#
# Arte: folha 8 direções x N quadros do FreePixel — ver arte/LEIA-ME.md.

signal morreu(inimigo: Node)

const VELOCIDADE := 130.0        # mais lento que a party, dá pra fugir
const RAIO := 20.0
const VIDA_MAXIMA := 50
const DANO_CONTATO := 10
const COOLDOWN_DANO := 0.8
const ALCANCE_CONTATO := 48.0    # raio do inimigo (20) + raio da party (24) + folga
const TEMPO_MACHUCADO := 0.15
const TEMPO_SUMINDO := 0.55   # curto de proposito: sem quadro de morte, o
                              # corpo e o sprite girado 90 graus, e girado
                              # sobre a grama ele vira so uma mancha escura.
                              # Quanto menos tempo na tela, melhor.

const ESCALA_SPRITE := 0.72       # o quadro original é 128x128
const ALTURA_SPRITE := -32.0

const CHANCE_DE_LARGAR_ITEM := 0.35
const ITENS_QUE_LARGA := ["kit", "escudo", "turbo", "estouro", "veloz", "foco"]

var vida := VIDA_MAXIMA
var neutro := false : set = _define_neutro

var _sprite: AnimatedSprite2D
var _morto := false
var _tempo_ate_proximo_dano := 0.0
var _tempo_machucado := 0.0
var _tempo_sumindo := 0.0
var _tempo_lentidao := 0.0
var _fator_lentidao := 1.0
var _tempo_preso := 0.0

func _ready() -> void:
	var forma := CircleShape2D.new()
	forma.radius = RAIO
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

	# Zera antes de configurar (a Godot liga o bit 1 sozinha nos dois campos).
	collision_layer = 0
	collision_mask = 0
	set_collision_layer_value(2, true)   # camada 2 = inimigos
	set_collision_mask_value(1, true)    # esbarra na party
	set_collision_mask_value(2, true)    # e nos outros inimigos

	add_to_group("inimigos")

	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = load("res://Animacoes_goblin.tres")
	_sprite.scale = Vector2(ESCALA_SPRITE, ESCALA_SPRITE)
	_sprite.position = Vector2(0, ALTURA_SPRITE)
	_sprite.play("parado_0")
	add_child(_sprite)

func _define_neutro(valor: bool) -> void:
	neutro = valor
	if is_inside_tree() and _sprite != null:
		_atualiza_sprite(Vector2.RIGHT, false)

func _physics_process(delta: float) -> void:
	# --- Já morreu: só termina de sumir ---
	if _morto:
		_tempo_sumindo -= delta
		_sprite.modulate.a = clamp(_tempo_sumindo / TEMPO_SUMINDO, 0.0, 1.0)
		if _tempo_sumindo <= 0.0:
			queue_free()
		return

	_tempo_machucado = max(0.0, _tempo_machucado - delta)
	_tempo_preso = max(0.0, _tempo_preso - delta)
	_tempo_lentidao = max(0.0, _tempo_lentidao - delta)
	if _tempo_lentidao <= 0.0:
		_fator_lentidao = 1.0

	var alvo := _membro_mais_perto()
	if alvo == null:
		return   # party toda no chão: não há quem perseguir

	var ate_o_alvo: Vector2 = alvo.global_position - global_position

	# Preso pelas raízes: não anda, mas ainda leva tiro e ainda machuca quem
	# estiver colado nele.
	var andando := _tempo_preso <= 0.0
	if andando:
		velocity = ate_o_alvo.normalized() * VELOCIDADE * _fator_lentidao
		move_and_slide()
	else:
		velocity = Vector2.ZERO

	# --- Dano por encostar (com intervalo, senão drena a vida num piscar) ---
	_tempo_ate_proximo_dano -= delta
	if not neutro and ate_o_alvo.length() <= ALCANCE_CONTATO and _tempo_ate_proximo_dano <= 0.0:
		alvo.receber_dano(DANO_CONTATO)
		_tempo_ate_proximo_dano = COOLDOWN_DANO

	_atualiza_sprite(ate_o_alvo, andando)
	queue_redraw()

# Com dois na party, o inimigo vai atrás do membro VIVO mais próximo -- e não
# do primeiro do grupo, senão os dois seriam sempre puxados para a mesma pessoa.
func _membro_mais_perto() -> Node2D:
	var melhor: Node2D = null
	var menor := INF
	for membro in get_tree().get_nodes_in_group("jogador"):
		if membro.vida <= 0:
			continue
		var dist: float = global_position.distance_to(membro.global_position)
		if dist < menor:
			menor = dist
			melhor = membro
	return melhor

# Mesma conversão de ângulo em linha da folha usada no Personagem.gd.
func _linha_da_direcao(d: Vector2) -> int:
	if d == Vector2.ZERO:
		return 0
	var graus := rad_to_deg(atan2(d.y, d.x))
	if graus < 0.0:
		graus += 360.0
	return (int(round(graus / 45.0)) + 6) % 8

func _atualiza_sprite(para_o_alvo: Vector2, andando: bool) -> void:
	var cor := Color.WHITE
	if _tempo_machucado > 0.0:
		cor = Color(1, 0.5, 0.5)
	elif _tempo_preso > 0.0:
		cor = Color(0.75, 0.9, 0.6)      # esverdeado: preso pelas raízes
	elif _tempo_lentidao > 0.0:
		cor = Color(0.65, 0.85, 1.0)     # azulado: lento
	if neutro:
		cor.a = 0.75                     # translúcido = está desarmado
	_sprite.modulate = cor

	var estado := "andando" if andando else "parado"
	var nome := "%s_%d" % [estado, _linha_da_direcao(para_o_alvo)]
	if _sprite.animation != nome:
		_sprite.play(nome)

# --- Dano, lentidão e raízes ------------------------------------------------

func receber_dano(quantidade: int) -> void:
	if _morto:
		return
	vida -= quantidade
	_tempo_machucado = TEMPO_MACHUCADO
	queue_redraw()
	if vida <= 0:
		_morrer()

func aplicar_lentidao(fator: float, tempo: float) -> void:
	if _morto:
		return
	_fator_lentidao = clamp(1.0 - fator, 0.15, 1.0)
	_tempo_lentidao = tempo

func prender(tempo: float) -> void:
	if _morto:
		return
	_tempo_preso = tempo
	queue_redraw()

func _morrer() -> void:
	_morto = true
	_tempo_sumindo = TEMPO_SUMINDO

	# Avisa a Main NA HORA (o contador da onda não espera o corpo sumir).
	morreu.emit(self)

	# Sai do jogo: não conta mais como inimigo, não leva tiro, não empurra.
	remove_from_group("inimigos")
	collision_layer = 0
	collision_mask = 0
	velocity = Vector2.ZERO
	# Esta arte não tem quadro de morte: deita o boneco.
	_sprite.rotation = deg_to_rad(90.0)
	_sprite.modulate = Color.WHITE
	queue_redraw()

	_talvez_largar_item()

func _talvez_largar_item() -> void:
	if randf() >= CHANCE_DE_LARGAR_ITEM:
		return
	var item: Area2D = load("res://Item.gd").new()
	item.tipo = ITENS_QUE_LARGA[randi() % ITENS_QUE_LARGA.size()]
	item.global_position = global_position
	# call_deferred: isto aqui roda dentro do passo de física (veio do sinal
	# body_entered da bala), e a Godot reclama se a cena mudar no meio dele.
	get_parent().call_deferred("add_child", item)

# Quem desenha a barra e a camada BarrasNaTela.gd. So aparece depois do
# primeiro dano, e sem coracao -- coracao e coisa da party.
func dados_da_barra() -> Dictionary:
	if _morto or vida >= VIDA_MAXIMA:
		return {}
	return {
		"altura": -74.0,
		"largura": 34.0,
		"vida": max(vida, 0),
		"vida_maxima": VIDA_MAXIMA,
		"coracao": false,
		"cor_extra": Color(0, 0, 0, 0),
		"marca": false,
		"riscos": 0,
	}

func _draw() -> void:
	if _morto:
		return   # sem sombra nem barra de vida depois de cair

	# Sombra no chão
	draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.42))
	draw_circle(Vector2.ZERO, RAIO * 0.85, Color(0, 0, 0, 0.35))
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

	# Preso: raízes saindo do chão em volta dos pés
	if _tempo_preso > 0.0:
		# MARROM, nao verde: raiz verde sobre grama verde fica invisivel.
		var cor_raiz := Color(0.28, 0.16, 0.06)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.45))
		draw_arc(Vector2.ZERO, RAIO * 1.15, 0.0, TAU, 24, cor_raiz, 4.0)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		for i in 8:
			var a := TAU * (float(i) / 8.0)
			var pe := Vector2(cos(a), sin(a) * 0.45) * (RAIO * 1.05)
			draw_line(pe, pe + Vector2(0, -22.0), cor_raiz, 5.0)

	# Barra de vida, só aparece depois do primeiro dano
