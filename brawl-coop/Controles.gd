extends Node
# Teclas do jogo, configuráveis pelo jogador (autoload).
#
# Em vez de "if Input.is_physical_key_pressed(KEY_W)" espalhado pelo código, o
# jogo pergunta por AÇÃO: Input.is_action_pressed("andar_cima"). Quem diz qual
# tecla é cada ação é o InputMap da Godot -- e é por isso que dá para trocar a
# tecla em tempo de execução sem mexer em script nenhum.
#
# O que o jogador configurar fica em user://controles.cfg e volta na próxima
# abertura. Apagar esse arquivo devolve tudo ao padrão.

signal controles_mudaram

const ARQUIVO := "user://controles.cfg"

# ordem = ordem que aparece na tela de configuração
const ACOES := [
	{"id": "andar_cima",   "nome": "Andar para cima",     "padrao": KEY_W},
	{"id": "andar_baixo",  "nome": "Andar para baixo",    "padrao": KEY_S},
	{"id": "andar_esq",    "nome": "Andar para esquerda", "padrao": KEY_A},
	{"id": "andar_dir",    "nome": "Andar para direita",  "padrao": KEY_D},
	{"id": "atacar",       "nome": "Atacar",              "padrao": MOUSE_BUTTON_LEFT, "mouse": true},
	{"id": "habilidade",   "nome": "Habilidade da classe", "padrao": KEY_Q},
	{"id": "item_1",       "nome": "Item 1",              "padrao": KEY_1},
	{"id": "item_2",       "nome": "Item 2",              "padrao": KEY_2},
	{"id": "item_3",       "nome": "Item 3",              "padrao": KEY_3},
	{"id": "item_4",       "nome": "Item 4",              "padrao": KEY_4},
	{"id": "item_5",       "nome": "Item 5",              "padrao": KEY_5},
	{"id": "item_6",       "nome": "Item 6",              "padrao": KEY_6},
	{"id": "usar_item",    "nome": "Usar o item",         "padrao": KEY_E},
	{"id": "trocar_alvo",  "nome": "Trocar alvo do item", "padrao": KEY_T},
	{"id": "neutro",       "nome": "Inimigos neutros",    "padrao": KEY_N},
	{"id": "recomecar",    "nome": "Recomeçar",           "padrao": KEY_R},
]

func _init() -> void:
	# _init e nao _ready: as acoes precisam existir antes de qualquer cena
	# perguntar por elas.
	for acao in ACOES:
		if not InputMap.has_action(acao["id"]):
			InputMap.add_action(acao["id"])
		_troca_evento(acao["id"], _evento_padrao(acao))
	_carrega()

# --- Consulta ---------------------------------------------------------------

# Nome legível da tecla de uma ação, para mostrar na tela ("W", "Botão esq.").
func tecla_de(id: String) -> String:
	var eventos := InputMap.action_get_events(id)
	if eventos.is_empty():
		return "—"
	return texto_do_evento(eventos[0])

static func texto_do_evento(evento: InputEvent) -> String:
	if evento is InputEventKey:
		return OS.get_keycode_string(evento.physical_keycode)
	if evento is InputEventMouseButton:
		match evento.button_index:
			MOUSE_BUTTON_LEFT: return "Botão esq."
			MOUSE_BUTTON_RIGHT: return "Botão dir."
			MOUSE_BUTTON_MIDDLE: return "Botão meio"
			_: return "Botão %d" % evento.button_index
	return "?"

# Se outra ação já usa esse evento, devolve o id dela (para avisar o jogador).
func quem_ja_usa(evento: InputEvent, ignorando: String) -> String:
	for acao in ACOES:
		if acao["id"] == ignorando:
			continue
		for e in InputMap.action_get_events(acao["id"]):
			if _mesmo_evento(e, evento):
				return acao["id"]
	return ""

func nome_da_acao(id: String) -> String:
	for acao in ACOES:
		if acao["id"] == id:
			return acao["nome"]
	return id

# --- Configurar -------------------------------------------------------------

# Troca a tecla de uma ação. Se a tecla estava em outra ação, a outra fica SEM
# tecla -- de propósito: duas ações na mesma tecla brigariam em silêncio, e é
# melhor o jogador ver o "—" e resolver.
func define(id: String, evento: InputEvent) -> String:
	var conflito := quem_ja_usa(evento, id)
	if conflito != "":
		InputMap.action_erase_events(conflito)
	_troca_evento(id, evento)
	_salva()
	controles_mudaram.emit()
	return conflito

func restaura_padrao() -> void:
	for acao in ACOES:
		_troca_evento(acao["id"], _evento_padrao(acao))
	_salva()
	controles_mudaram.emit()

# --- Disco ------------------------------------------------------------------

func _salva() -> void:
	var cfg := ConfigFile.new()
	for acao in ACOES:
		var eventos := InputMap.action_get_events(acao["id"])
		if eventos.is_empty():
			cfg.set_value("controles", acao["id"], {"tipo": "nenhum"})
		elif eventos[0] is InputEventMouseButton:
			cfg.set_value("controles", acao["id"], {"tipo": "mouse", "codigo": eventos[0].button_index})
		else:
			cfg.set_value("controles", acao["id"], {"tipo": "tecla", "codigo": eventos[0].physical_keycode})
	cfg.save(ARQUIVO)

func _carrega() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(ARQUIVO) != OK:
		return   # primeira vez: fica no padrão
	for acao in ACOES:
		var dado = cfg.get_value("controles", acao["id"], null)
		if typeof(dado) != TYPE_DICTIONARY:
			continue
		match dado.get("tipo", ""):
			"nenhum":
				InputMap.action_erase_events(acao["id"])
			"mouse":
				var em := InputEventMouseButton.new()
				em.button_index = int(dado["codigo"])
				_troca_evento(acao["id"], em)
			"tecla":
				var ek := InputEventKey.new()
				ek.physical_keycode = int(dado["codigo"])
				_troca_evento(acao["id"], ek)

# --- Apoio ------------------------------------------------------------------

func _evento_padrao(acao: Dictionary) -> InputEvent:
	if acao.get("mouse", false):
		var em := InputEventMouseButton.new()
		em.button_index = acao["padrao"]
		return em
	var ek := InputEventKey.new()
	ek.physical_keycode = acao["padrao"]
	return ek

func _troca_evento(id: String, evento: InputEvent) -> void:
	InputMap.action_erase_events(id)
	InputMap.action_add_event(id, evento)

static func _mesmo_evento(a: InputEvent, b: InputEvent) -> bool:
	if a is InputEventKey and b is InputEventKey:
		return a.physical_keycode == b.physical_keycode
	if a is InputEventMouseButton and b is InputEventMouseButton:
		return a.button_index == b.button_index
	return false
