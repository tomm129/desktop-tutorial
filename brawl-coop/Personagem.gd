extends CharacterBody2D
# Personagem jogável de uma CLASSE. O mesmo script serve para os dois membros
# da party: o seu (por_ia = false, no teclado) e o aliado (por_ia = true).
# Todos os números vêm de Classes.gd — aqui não tem valor de classe chumbado.
#
#   Movimento: W A S D   |  Mira: mouse  |  Atacar: botão esquerdo
#   Habilidade: Q        |  Inventário: 1-4, T troca o alvo, E usa
#
# Arte: folhas 8 direções x N quadros do FreePixel — ver arte/LEIA-ME.md.
# A animação tocada é "parado_<linha>" ou "andando_<linha>", onde a linha sai
# da direção para onde o personagem está olhando (_linha_da_direcao).

signal vida_mudou(vida_atual: int)
signal recurso_mudou(quanto: float)
signal inventario_mudou
signal habilidade_usada(nome_da_hab: String)
signal morreu

const RAIO := 24.0               # círculo de colisão, no plano do chão
const TEMPO_INVULNERAVEL := 0.2  # carência sem levar dano depois de ser atingido.
                                 # Curta de propósito: se for longa (0.5s), ela
                                 # absorve o dano dos outros inimigos e uma onda
                                 # de 7 machuca igual a uma de 3.
const ESCALA_SPRITE := 0.9      # o quadro original é 128x128
const ALTURA_SPRITE := -38.0     # sobe o boneco: os pés ficam na base do círculo
const TEMPO_MACHUCADO := 0.18
const EMPURRAO_AO_APANHAR := 190.0   # quanto o golpe joga voce para tras
const TREMOR_AO_APANHAR := 5.0
const TEMPO_DO_GOLPE := 0.16     # quanto tempo o arco do golpe fica desenhado
const DURACAO_DA_INVESTIDA := 0.18
const ABERTURA_DO_GOLPE := 55.0  # meio-ângulo do leque do corpo a corpo

# --- Itens (iguais para todas as classes) ---
const CURA_DO_KIT := 40
const DURACAO_DO_ESCUDO := 4.0
const DURACAO_DO_TURBO := 6.0
const DURACAO_DA_VELOCIDADE := 6.0
const BONUS_DE_VELOCIDADE := 1.5     # 50% mais rapido enquanto dura
const DANO_DO_ESTOURO := 60
const RAIO_DO_ESTOURO := 130.0
const MAXIMO_POR_ITEM := 9

# --- Ajustes da IA do aliado ---
const IA_DISTANCIA_DO_LIDER := 120.0
const IA_RECUO_DO_INIMIGO := 95.0
const IA_VIDA_PARA_HABILIDADE := 0.6

@export var classe := "guerreiro"
@export var por_ia := false
# Personagem de OUTRA maquina: nao decide nada aqui, a posicao dele chega pela
# rede. Sem isso o seu teclado moveria todos os bonecos da tela.
@export var remoto := false
var id_de_rede := 0
var lider: Node2D                # a IA anda perto de quem está aqui

var vida := 100
var vida_maxima := 100
# Recurso da classe (Furia, Mana, Energia...). Ver Classes.gd.
var recurso := 0.0
var recurso_maximo := 100.0
var estoque := {"kit": 2, "escudo": 1, "turbo": 1, "estouro": 1, "veloz": 0, "foco": 0}

var _d := {}                     # os dados da classe, lidos uma vez
var _sprite: AnimatedSprite2D
var _mira := Vector2.RIGHT
var _tempo_ate_proximo_ataque := 0.0
var _tempo_invulneravel := 0.0
var _tempo_machucado := 0.0
var _tempo_escudo := 0.0
var _tempo_turbo := 0.0
var _tempo_veloz := 0.0
var _tempo_golpe := 0.0
var _recarga := 0.0
var _empurrao := Vector2.ZERO   # recuo de quem acabou de apanhar
# Aura (clérigo) e o "brilho" que as outras habilidades deixam na tela
var _tempo_aura := 0.0
var _cura_acumulada := 0.0
var _tempo_efeito := 0.0
var _raio_efeito := 0.0
# Investida (assassino)
var _tempo_investida := 0.0
var _atingidos := []

func _ready() -> void:
	_d = Classes.dados(classe)
	vida_maxima = int(_d["vida"])
	vida = vida_maxima
	recurso_maximo = float(_d.get("recurso_max", 100))
	# Quem enche batendo comeca VAZIO (a furia se conquista na briga); quem
	# enche com o tempo comeca cheio.
	recurso = 0.0 if _d.get("recurso_tipo", "tempo") == "combate" else recurso_maximo

	var forma := CircleShape2D.new()
	forma.radius = RAIO
	var col := CollisionShape2D.new()
	col.shape = forma
	add_child(col)

	# Zera antes de configurar (a Godot liga o bit 1 sozinha nos dois campos).
	collision_layer = 0
	collision_mask = 0
	set_collision_layer_value(1, true)   # camada 1 = party
	set_collision_mask_value(2, true)    # esbarra no corpo dos inimigos

	# Os inimigos perseguem o membro da party mais perto: os dois entram aqui.
	add_to_group("jogador")

	_sprite = AnimatedSprite2D.new()
	_sprite.sprite_frames = load(Classes.animacoes(classe))
	_sprite.scale = Vector2(ESCALA_SPRITE, ESCALA_SPRITE)
	_sprite.position = Vector2(0, ALTURA_SPRITE)
	_sprite.play("parado_0")
	add_child(_sprite)   # filho desenha DEPOIS do _draw(), ou seja, por cima da sombra

# Chamado quando chega pela rede o estado do dono deste personagem.
func aplica_estado_remoto(pos: Vector2, mira: Vector2, vida_dele: int) -> void:
	# A diferenca de posicao vira "velocidade" so para escolher entre a
	# animacao de parado e a de andando.
	velocity = (pos - global_position) * 10.0
	global_position = pos
	_mira = mira
	if vida_dele != vida:
		vida = vida_dele
		vida_mudou.emit(vida)
	queue_redraw()

func mira() -> Vector2:
	return _mira

func cor_da_classe() -> Color:
	return _d.get("cor", Color.WHITE)

func nome_da_classe() -> String:
	return _d.get("nome", classe)

func nome_da_habilidade() -> String:
	return _d.get("hab_nome", "Habilidade")

# --- Laço principal ---------------------------------------------------------

func _physics_process(delta: float) -> void:
	_passa_o_tempo(delta)

	if vida <= 0:
		_atualiza_sprite(Vector2.ZERO)
		queue_redraw()
		return   # caído não anda nem ataca

	var direcao := Vector2.ZERO
	if remoto:
		# Quem manda nele e a outra maquina; aqui so mostramos o que chegou.
		_atualiza_sprite(velocity)
		queue_redraw()
		return
	if _tempo_investida > 0.0:
		direcao = _corre_investida()
	else:
		direcao = _decide_ia() if por_ia else _decide_teclado()

	var rapidez := float(_d["velocidade"])
	if _tempo_veloz > 0.0:
		rapidez *= BONUS_DE_VELOCIDADE
	velocity = direcao.normalized() * rapidez + _empurrao
	if _tempo_investida > 0.0:
		velocity = _mira * (float(_d.get("hab_distancia", 260.0)) / DURACAO_DA_INVESTIDA)
	move_and_slide()

	# Não deixa sair da arena
	var tela := get_viewport_rect().size
	global_position.x = clamp(global_position.x, RAIO, tela.x - RAIO)
	global_position.y = clamp(global_position.y, RAIO, tela.y - RAIO)

	_atualiza_sprite(direcao)
	queue_redraw()

func _passa_o_tempo(delta: float) -> void:
	_tempo_ate_proximo_ataque -= delta
	_tempo_invulneravel = max(0.0, _tempo_invulneravel - delta)
	_tempo_machucado = max(0.0, _tempo_machucado - delta)
	_tempo_escudo = max(0.0, _tempo_escudo - delta)
	_tempo_turbo = max(0.0, _tempo_turbo - delta)
	_tempo_veloz = max(0.0, _tempo_veloz - delta)
	_tempo_golpe = max(0.0, _tempo_golpe - delta)
	# Sem esta linha a investida NUNCA acaba: o personagem sai voando na
	# direcao da mira ate grudar na borda da tela, sem responder ao teclado
	# (durante a investida o _decide_teclado nem chega a ser chamado).
	_tempo_investida = max(0.0, _tempo_investida - delta)
	_tempo_efeito = max(0.0, _tempo_efeito - delta)
	_recarga = max(0.0, _recarga - delta)
	if _d.get("recurso_tipo", "tempo") == "tempo":
		_muda_recurso(float(_d.get("recurso_regen", 0.0)) * delta)
	_empurrao = _empurrao.lerp(Vector2.ZERO, min(1.0, delta * 9.0))

	if _tempo_aura > 0.0:
		_tempo_aura = max(0.0, _tempo_aura - delta)
		_pulsa_aura(delta)

# --- Vontade: teclado ou IA -------------------------------------------------

func _decide_teclado() -> Vector2:
	# Pergunta por ACAO e nao por tecla: e o que deixa o jogador remapear tudo
	# na tela de controles (ver Controles.gd).
	var direcao := Vector2.ZERO
	if Input.is_action_pressed("andar_cima"): direcao.y -= 1
	if Input.is_action_pressed("andar_baixo"): direcao.y += 1
	if Input.is_action_pressed("andar_esq"): direcao.x -= 1
	if Input.is_action_pressed("andar_dir"): direcao.x += 1

	_mira = (get_global_mouse_position() - global_position).normalized()
	if Input.is_action_pressed("atacar"):
		_tenta_atacar()
	return direcao

# O aliado: mira no inimigo mais perto, ataca dentro do alcance da classe,
# recua se colarem nele, solta a habilidade quando a party se machuca, e no
# resto do tempo fica por perto de você.
func _decide_ia() -> Vector2:
	var inimigo := _inimigo_mais_perto()

	if inimigo != null:
		var ate_ele: Vector2 = inimigo.global_position - global_position
		_mira = ate_ele.normalized()
		var alcance := float(_d.get("alcance", 300))
		if ate_ele.length() <= alcance:
			_tenta_atacar()

		# Corpo a corpo precisa CHEGAR perto; quem atira de longe recua.
		if _d["ataque"] == "arco":
			if ate_ele.length() > alcance * 0.7:
				return ate_ele.normalized()
		elif ate_ele.length() < IA_RECUO_DO_INIMIGO:
			return -ate_ele.normalized()

	if _recarga <= 0.0 and _vale_a_pena_habilidade(inimigo):
		ativar_habilidade()

	if lider != null:
		var ate_o_lider: Vector2 = lider.global_position - global_position
		if ate_o_lider.length() > IA_DISTANCIA_DO_LIDER:
			return ate_o_lider.normalized()
	return Vector2.ZERO

# Cura/escudo quando alguém está ferido; as ofensivas, quando há inimigo perto.
func _vale_a_pena_habilidade(inimigo: Node2D) -> bool:
	var raio := float(_d.get("hab_raio", 150.0))
	if _d["habilidade"] in ["aura", "escudo"]:
		for membro in get_tree().get_nodes_in_group("jogador"):
			if membro.vida > 0 and float(membro.vida) / float(membro.vida_maxima) < IA_VIDA_PARA_HABILIDADE \
				and global_position.distance_to(membro.global_position) <= raio:
				return true
		return false
	return inimigo != null and global_position.distance_to(inimigo.global_position) <= raio

func _inimigo_mais_perto() -> Node2D:
	var melhor: Node2D = null
	var menor := INF
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		var dist: float = global_position.distance_to(inimigo.global_position)
		if dist < menor:
			menor = dist
			melhor = inimigo
	return melhor

# --- Recurso ----------------------------------------------------------------

func _muda_recurso(quanto: float) -> void:
	var antes := recurso
	recurso = clampf(recurso + quanto, 0.0, recurso_maximo)
	if not is_equal_approx(antes, recurso):
		recurso_mudou.emit(recurso)

func tem_recurso(quanto: float) -> bool:
	return recurso >= quanto

func nome_do_recurso() -> String:
	return _d.get("recurso", "Recurso")

func cor_do_recurso() -> Color:
	return _d.get("cor_recurso", Color.WHITE)

# Furia e Fervor sobem batendo e apanhando: e o que faz o guerreiro querer
# estar no meio da briga em vez de esperar recarga.
func _ganha_no_combate(fator := 1.0) -> void:
	if _d.get("recurso_tipo", "tempo") == "combate":
		_muda_recurso(float(_d.get("recurso_ganho", 0)) * fator)

# --- Ataque -----------------------------------------------------------------

func _tenta_atacar() -> void:
	if _tempo_ate_proximo_ataque > 0.0:
		return
	# Classes que gastam recurso por golpe (mago, arqueiro, assassino) param de
	# atirar quando acaba -- e o que impede segurar o botao a partida inteira.
	var custo := float(_d.get("custo_ataque", 0))
	if custo > 0.0 and not tem_recurso(custo):
		return
	_muda_recurso(-custo)
	match _d["ataque"]:
		"arco": _golpe_em_arco()
		_: _dispara(_mira)
	# O turbo (item) dobra a cadência de qualquer classe.
	_tempo_ate_proximo_ataque = float(_d["cadencia"]) * (0.5 if _tempo_turbo > 0.0 else 1.0)

# Corpo a corpo: acerta todo mundo num leque à frente, sem projétil nenhum.
func _golpe_em_arco() -> void:
	var alcance := float(_d.get("alcance", 70.0))
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		var ate_ele: Vector2 = inimigo.global_position - global_position
		if ate_ele.length() <= alcance + RAIO \
			and absf(_mira.angle_to(ate_ele)) <= deg_to_rad(ABERTURA_DO_GOLPE):
			inimigo.receber_dano(int(_d["dano"]), global_position)
			_ganha_no_combate()
			Efeitos.faisca(get_parent(), inimigo.global_position + Vector2(0, -22),
				Color(1, 0.9, 0.6), 8, 110.0)
	# Corte desenhado na direcao da mira, no lugar do arco branco simples.
	Efeitos.desenhado(get_parent(), global_position + _mira * (RAIO + 18.0), "corte",
		float(_d.get("alcance", 70.0)) * 1.9, 0.28, 0.0, Color.WHITE, _mira.angle())
	_tempo_golpe = TEMPO_DO_GOLPE

func _dispara(direcao: Vector2) -> void:
	var bala: Area2D = load("res://Bala.gd").new()
	bala.direcao = direcao
	bala.dano = int(_d["dano"])
	bala.cor = _d.get("cor", Color(1.0, 0.85, 0.2))
	bala.alcance = float(_d.get("alcance", 450.0))
	if _d["ataque"] == "explosivo":
		bala.raio_estouro = float(_d.get("raio_estouro", 70.0))
		bala.dano_estouro = int(_d.get("dano_estouro", 20))
	elif _d["ataque"] == "gelado":
		bala.lentidao = float(_d.get("lentidao", 0.5))
		bala.tempo_lentidao = float(_d.get("tempo_lentidao", 2.0))
	bala.global_position = global_position + direcao * (RAIO + 6.0)
	get_parent().add_child(bala)

	# Avisa as outras maquinas para o tiro APARECER na tela delas. Sem isso o
	# dano dos parceiros acontece, mas ninguem ve os projeteis deles.
	var principal := get_tree().get_first_node_in_group("main")
	if principal != null:
		principal.avisa_tiro(bala.global_position, direcao, classe)

# --- Habilidade (tecla Q) ---------------------------------------------------

func ativar_habilidade() -> bool:
	if vida <= 0 or _recarga > 0.0:
		return false
	var custo := float(_d.get("custo_hab", 0))
	if not tem_recurso(custo):
		return false
	var raio := float(_d.get("hab_raio", 150.0))

	match _d["habilidade"]:
		"aura":
			_tempo_aura = float(_d.get("hab_duracao", 4.0))
			_cura_acumulada = 0.0
			Efeitos.desenhado(get_parent(), global_position, "cura", raio * 1.6, 0.8, 0.6)
		"giro", "nova":
			for inimigo in get_tree().get_nodes_in_group("inimigos"):
				if global_position.distance_to(inimigo.global_position) <= raio:
					inimigo.receber_dano(int(_d.get("hab_dano", 50)), global_position)
					Efeitos.faisca(get_parent(), inimigo.global_position + Vector2(0, -24),
						_d.get("cor", Color.WHITE), 14, 200.0)
			Efeitos.poeira(get_parent(), global_position)
			# Nova desenhada por cima do anel: e o que faz a habilidade parecer
			# uma habilidade, e nao um circulo crescendo.
			Efeitos.desenhado(get_parent(), global_position, "nova", raio * 2.0, 0.55,
				3.0, _d.get("cor", Color.WHITE))
			_mostra_efeito(raio)
		"escudo":
			for membro in get_tree().get_nodes_in_group("jogador"):
				if membro.vida > 0 and global_position.distance_to(membro.global_position) <= raio:
					membro.aplicar_efeito("escudo")
					Efeitos.faisca(get_parent(), membro.global_position + Vector2(0, -30),
						Color(0.5, 0.85, 1.0), 12, 90.0)
					Efeitos.desenhado(get_parent(), membro.global_position + Vector2(0, -22),
						"escudo", 110.0, 0.7)
			_mostra_efeito(raio)
		"leque":
			var tiros := int(_d.get("hab_tiros", 5))
			var abertura := deg_to_rad(float(_d.get("hab_abertura", 60.0)))
			for i in tiros:
				var passo := abertura / float(max(tiros - 1, 1))
				_dispara(_mira.rotated(-abertura / 2.0 + passo * i))
		"raizes":
			for inimigo in get_tree().get_nodes_in_group("inimigos"):
				if global_position.distance_to(inimigo.global_position) <= raio:
					inimigo.prender(float(_d.get("hab_duracao", 2.5)))
					Efeitos.poeira(get_parent(), inimigo.global_position)
					Efeitos.faisca(get_parent(), inimigo.global_position,
						Color(0.35, 0.55, 0.2), 10, 80.0)
					Efeitos.desenhado(get_parent(), inimigo.global_position, "raizes", 90.0, 0.6, 1.2)
			_mostra_efeito(raio)
		"investida":
			_tempo_investida = DURACAO_DA_INVESTIDA
			_atingidos.clear()
		_:
			return false

	_muda_recurso(-float(_d.get("custo_hab", 0)))
	_recarga = float(_d.get("recarga", 10.0))
	habilidade_usada.emit(nome_da_habilidade())
	return true

const DURACAO_DO_EFEITO := 0.5

func _mostra_efeito(raio: float) -> void:
	_tempo_efeito = DURACAO_DO_EFEITO
	_raio_efeito = raio

# Enquanto avança, machuca quem atravessar — cada inimigo só uma vez.
func _corre_investida() -> Vector2:
	for inimigo in get_tree().get_nodes_in_group("inimigos"):
		if inimigo in _atingidos:
			continue
		if global_position.distance_to(inimigo.global_position) <= RAIO + 26.0:
			inimigo.receber_dano(int(_d.get("hab_dano", 45)), global_position)
			Efeitos.faisca(get_parent(), inimigo.global_position + Vector2(0, -24),
				Color(1, 1, 1), 14, 190.0)
			_atingidos.append(inimigo)
	return _mira

func _pulsa_aura(delta: float) -> void:
	_cura_acumulada += float(_d.get("hab_cura", 10.0)) * delta
	var pontos := int(_cura_acumulada)
	if pontos <= 0:
		return
	_cura_acumulada -= float(pontos)
	var raio := float(_d.get("hab_raio", 145.0))
	for membro in get_tree().get_nodes_in_group("jogador"):
		if membro.vida > 0 and global_position.distance_to(membro.global_position) <= raio:
			membro.curar(pontos)

func habilidade_pronta() -> bool:
	return _recarga <= 0.0

# Recarga cheia da classe, para a barra de habilidade saber a fracao.
func recarga_total() -> float:
	return float(_d.get("recarga", 10.0))

func recarga_restante() -> float:
	return _recarga

func aura_ativa() -> bool:
	return _tempo_aura > 0.0

# --- Inventário -------------------------------------------------------------

# O aliado não cata itens: deixa no chão para você.
func pegar_item(tipo: String) -> bool:
	if vida <= 0 or por_ia:
		return false
	var quantos: int = estoque.get(tipo, 0)
	if quantos >= MAXIMO_POR_ITEM:
		return false
	estoque[tipo] = quantos + 1
	inventario_mudou.emit()
	return true

# Quem GASTA o item é este personagem; quem RECEBE o efeito é "alvo".
# É isso que deixa mandar o kit no aliado em vez de usar em você.
func usar_item(tipo: String, alvo: Node = null) -> bool:
	if alvo == null:
		alvo = self
	if vida <= 0 or estoque.get(tipo, 0) <= 0:
		return false
	if not alvo.pode_receber(tipo):
		return false
	alvo.aplicar_efeito(tipo)
	estoque[tipo] -= 1
	inventario_mudou.emit()
	return true

# Recusa o que seria desperdício (kit com a vida cheia, qualquer coisa em quem
# já caiu). É o que faz o item não sumir à toa.
func pode_receber(tipo: String) -> bool:
	if vida <= 0:
		return false
	match tipo:
		"kit": return vida < vida_maxima          # nao desperdica com vida cheia
		"foco": return _recarga > 0.0             # nem com a habilidade ja pronta
		_: return tipo in ["escudo", "turbo", "veloz", "estouro"]

func aplicar_efeito(tipo: String) -> void:
	match tipo:
		"kit": curar(CURA_DO_KIT)
		"escudo": _tempo_escudo = DURACAO_DO_ESCUDO
		"turbo": _tempo_turbo = DURACAO_DO_TURBO
		"veloz": _tempo_veloz = DURACAO_DA_VELOCIDADE
		"foco": _recarga = 0.0
		"estouro":
			# Estoura em volta de QUEM RECEBEU. Jogado no aliado cercado, e ele
			# quem limpa a volta dele -- por isso vale a pena mirar no parceiro.
			for inimigo in get_tree().get_nodes_in_group("inimigos"):
				if global_position.distance_to(inimigo.global_position) <= RAIO_DO_ESTOURO:
					inimigo.receber_dano(DANO_DO_ESTOURO, global_position)
					Efeitos.faisca(get_parent(), inimigo.global_position + Vector2(0, -24),
						Color(1.0, 0.5, 0.2), 16, 210.0)
			Efeitos.faisca(get_parent(), global_position, Color(1.0, 0.6, 0.2), 24, 260.0)
			Efeitos.desenhado(get_parent(), global_position, "estouro", RAIO_DO_ESTOURO * 2.0, 0.5)
			_mostra_efeito(RAIO_DO_ESTOURO)
	queue_redraw()

func curar(quantidade: int) -> void:
	if vida <= 0:
		return
	var antes := vida
	vida = min(vida_maxima, vida + quantidade)
	if vida != antes:
		Efeitos.numero_de_cura(get_parent(), global_position + Vector2(0, -66), vida - antes)
		vida_mudou.emit(vida)
		queue_redraw()

func tem_escudo() -> bool:
	return _tempo_escudo > 0.0

func tem_turbo() -> bool:
	return _tempo_turbo > 0.0

func tem_velocidade() -> bool:
	return _tempo_veloz > 0.0

# --- Dano e desenho ---------------------------------------------------------

func receber_dano(quantidade: int, de_onde := Vector2.ZERO) -> void:
	# Quem decide a vida de um personagem e a maquina do DONO dele. Se este
	# aqui e de outra pessoa, avisamos ela em vez de mexer na vida por conta --
	# senao cada maquina teria uma versao diferente da mesma vida.
	if remoto and id_de_rede != 0:
		var principal := get_tree().get_first_node_in_group("main")
		if principal != null:
			principal.avisa_dano_em_jogador(id_de_rede, quantidade)
		return
	if vida <= 0 or _tempo_invulneravel > 0.0 or _tempo_escudo > 0.0:
		return
	vida = max(0, vida - quantidade)
	_tempo_invulneravel = TEMPO_INVULNERAVEL
	_tempo_machucado = TEMPO_MACHUCADO
	_ganha_no_combate(1.5)   # apanhar da mais furia do que bater

	# O que faz a pancada PARECER pancada, ja que a arte nao tem quadro de dano:
	# recuo, faisca no peito, numero subindo e -- so para quem levou -- tremor.
	if de_onde != Vector2.ZERO:
		_empurrao = (global_position - de_onde).normalized() * EMPURRAO_AO_APANHAR
	Efeitos.faisca(get_parent(), global_position + Vector2(0, -34), Color(1.0, 0.45, 0.35), 12)
	Efeitos.numero(get_parent(), global_position + Vector2(0, -66), quantidade)
	if not por_ia and not remoto:
		var quem_manda := get_tree().get_first_node_in_group("main")
		if quem_manda != null:
			quem_manda.tremer(TREMOR_AO_APANHAR)

	vida_mudou.emit(vida)
	queue_redraw()
	if vida == 0:
		# Poe a pose de morte AQUI, e nao no _physics_process: a Main pausa a
		# arvore assim que recebe o sinal, e dai o _physics_process nao roda
		# mais nunca -- o boneco morreria em pe.
		_atualiza_sprite(Vector2.ZERO)
		morreu.emit()

# Converte a direção do olhar na LINHA da folha de sprite. A folha gira no
# sentido horário a partir de "olhando para baixo":
#   0 baixo | 1 baixo-esq | 2 esquerda | 3 cima-esq
#   4 cima  | 5 cima-dir  | 6 direita  | 7 baixo-dir
# Em ângulo de tela, 0 grau é para a direita (linha 6) e 90 graus é para baixo
# (linha 0) -- daí o "+6".
func _linha_da_direcao(d: Vector2) -> int:
	if d == Vector2.ZERO:
		return 0
	var graus := rad_to_deg(atan2(d.y, d.x))
	if graus < 0.0:
		graus += 360.0
	return (int(round(graus / 45.0)) + 6) % 8

func _atualiza_sprite(direcao: Vector2) -> void:
	_sprite.position = Vector2(0, ALTURA_SPRITE)

	if vida <= 0:
		# Esta arte não tem quadro de morte: deita o boneco e escurece.
		_sprite.rotation = deg_to_rad(90.0)
		_sprite.modulate = Color(0.55, 0.55, 0.6, 0.9)
		return
	_sprite.rotation = 0.0
	_sprite.modulate = Color(1, 0.55, 0.55) if _tempo_machucado > 0.0 else Color.WHITE

	var estado := "andando" if direcao != Vector2.ZERO else "parado"
	var nome := "%s_%d" % [estado, _linha_da_direcao(_mira)]
	if _sprite.animation != nome:
		_sprite.play(nome)   # só troca se for outra, senão reiniciaria todo quadro

# Quem desenha a barra e a camada BarrasNaTela.gd, por cima de todo mundo.
# Aqui so dizemos O QUE desenhar. Devolver {} = nao quero barra agora.
func dados_da_barra() -> Dictionary:
	return {
		"altura": -96.0,          # bem acima da cabeca
		"largura": 52.0,
		"vida": max(vida, 0),     # morto vira a barra cinza de 0%
		"vida_maxima": vida_maxima,
		"coracao": true,
		"cor_extra": _d.get("cor", Color.WHITE),
		"marca": por_ia,
		"riscos": 2 if por_ia else 1,
	}

func _draw() -> void:
	# ATENÇÃO: o que é desenhado aqui fica ATRÁS do sprite (o filho desenha
	# depois do pai). Por isso a sombra funciona, e a barra de vida fica acima
	# da cabeça, fora da área do boneco.
	var cor := _d.get("cor", Color.WHITE) as Color

	# Aura de cura ligada (clérigo)
	if _tempo_aura > 0.0:
		var pulso := 0.85 + 0.15 * sin(_tempo_aura * 8.0)
		var raio := float(_d.get("hab_raio", 145.0)) * pulso
		draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.45))
		draw_circle(Vector2.ZERO, raio, Color(0.35, 1.0, 0.5, 0.12))
		draw_arc(Vector2.ZERO, raio, 0.0, TAU, 48, Color(0.4, 1.0, 0.55, 0.8), 3.0)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

	# Estouro das habilidades de área (giro, nova, escudo, raízes)
	if _tempo_efeito > 0.0:
		var quanto := 1.0 - (_tempo_efeito / DURACAO_DO_EFEITO)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.45))
		# disco cheio + anel grosso: so o anel fino passava despercebido
		draw_circle(Vector2.ZERO, _raio_efeito * quanto,
			Color(cor.r, cor.g, cor.b, 0.30 * (1.0 - quanto)))
		draw_arc(Vector2.ZERO, _raio_efeito * quanto, 0.0, TAU, 48,
			Color(cor.r, cor.g, cor.b, 1.0 - quanto), 8.0)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

	# Sombra no chão
	draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, 0.42))
	draw_circle(Vector2.ZERO, RAIO * 0.85, Color(0, 0, 0, 0.35))
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

	if vida <= 0:
		return

	# Golpe corpo a corpo: leque na direção da mira
	if _tempo_golpe > 0.0:
		var alcance := float(_d.get("alcance", 70.0)) + RAIO
		var meio := deg_to_rad(ABERTURA_DO_GOLPE)
		var ang := _mira.angle()
		draw_arc(Vector2.ZERO, alcance * 0.9, ang - meio, ang + meio, 24,
			Color(1, 1, 1, _tempo_golpe / TEMPO_DO_GOLPE), 6.0)

	# Escudo ativo
	if _tempo_escudo > 0.0:
		draw_arc(Vector2(0, -20.0), RAIO + 16.0, 0.0, TAU, 40, Color(0.4, 0.8, 1.0, 0.9), 3.0)

	# Turbo ativo
	if _tempo_turbo > 0.0:
		for i in 3:
			var a := TAU * (float(i) / 3.0) + _tempo_turbo * 6.0
			var dir := Vector2(cos(a), sin(a) * 0.4)
			draw_line(dir * (RAIO + 4.0), dir * (RAIO + 14.0), Color(1.0, 0.85, 0.2, 0.9), 3.0)

	# Barra de vida acima da cabeça, na cor da classe
