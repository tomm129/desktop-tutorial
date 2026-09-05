extends Node
# Camada de rede (autoload). Partidas de até 4 jogadores.
#
# QUEM MANDA NO QUÊ (isso é o coração de um jogo em rede):
#
#   - Cada jogador manda no PRÓPRIO personagem: posição, mira e animação saem
#     da máquina dele e são avisadas para as outras. É o mais simples e o que
#     dá a sensação de controle imediato, sem esperar resposta do servidor.
#   - O ANFITRIÃO manda nos INIMIGOS: ele decide onde cada um está, quem eles
#     perseguem e quando causam dano. Se cada máquina simulasse os inimigos por
#     conta, cada uma veria uma partida diferente.
#   - Dano em inimigo é pedido ao anfitrião, que aplica e avisa todo mundo.
#
# CONEXÃO: é ENet direto por IP, como uma LAN. Para jogar pela internet, todos
# entram numa rede virtual (ZeroTier, Radmin) e usam o IP que ela dá -- foi a
# escolha do projeto para não depender de abrir porta no roteador, que não
# funciona em quem tem CGNAT.

signal lista_mudou
signal partida_comecou
signal desconectado(motivo: String)

const PORTA_PADRAO := 7777
const MAXIMO_DE_JOGADORES := 4

# id do peer -> {"nome": String, "classe": String}
var jogadores := {}
var sou_anfitriao := false
var em_partida := false
# Ligado de verdade? NAO da para perguntar isso ao multiplayer_peer: na Godot 4
# ele nunca e nulo -- vem um OfflineMultiplayerPeer por padrao, e ai qualquer
# teste de "esta em rede?" da verdadeiro ate numa partida local.
var _ligado := false

func _ready() -> void:
	multiplayer.peer_connected.connect(_ao_conectar_alguem)
	multiplayer.peer_disconnected.connect(_ao_sair_alguem)
	multiplayer.connected_to_server.connect(_ao_entrar_no_servidor)
	multiplayer.connection_failed.connect(_ao_falhar)
	multiplayer.server_disconnected.connect(_ao_cair_o_servidor)

func meu_id() -> int:
	return multiplayer.get_unique_id() if multiplayer.multiplayer_peer != null else 1

# --- Abrir e entrar ---------------------------------------------------------

func hospedar(nome: String, porta: int = PORTA_PADRAO) -> String:
	var peer := ENetMultiplayerPeer.new()
	var erro := peer.create_server(porta, MAXIMO_DE_JOGADORES - 1)
	if erro != OK:
		return "não deu para abrir a porta %d (erro %d)" % [porta, erro]
	multiplayer.multiplayer_peer = peer
	_ligado = true
	sou_anfitriao = true
	jogadores = {1: {"nome": nome, "classe": "guerreiro"}}
	lista_mudou.emit()
	return ""

func entrar(ip: String, nome: String, porta: int = PORTA_PADRAO) -> String:
	var peer := ENetMultiplayerPeer.new()
	var erro := peer.create_client(ip, porta)
	if erro != OK:
		return "não deu para falar com %s:%d (erro %d)" % [ip, porta, erro]
	multiplayer.multiplayer_peer = peer
	_ligado = true
	sou_anfitriao = false
	_meu_nome = nome
	return ""

func sair() -> void:
	if multiplayer.multiplayer_peer != null:
		multiplayer.multiplayer_peer.close()
	multiplayer.multiplayer_peer = null
	_ligado = false
	jogadores.clear()
	sou_anfitriao = false
	em_partida = false
	lista_mudou.emit()

func esta_em_rede() -> bool:
	return _ligado

var _meu_nome := "jogador"

# --- Entradas e saídas ------------------------------------------------------

func _ao_conectar_alguem(id: int) -> void:
	# Só o anfitrião mantém a lista de verdade; ele reenvia para todos.
	if not sou_anfitriao:
		return
	_manda_lista.rpc_id(id, jogadores)

func _ao_sair_alguem(id: int) -> void:
	if not sou_anfitriao:
		return
	jogadores.erase(id)
	_manda_lista.rpc(jogadores)
	lista_mudou.emit()

func _ao_entrar_no_servidor() -> void:
	_me_apresento.rpc_id(1, _meu_nome)

func _ao_falhar() -> void:
	multiplayer.multiplayer_peer = null
	_ligado = false
	desconectado.emit("não consegui conectar")

func _ao_cair_o_servidor() -> void:
	multiplayer.multiplayer_peer = null
	_ligado = false
	jogadores.clear()
	em_partida = false
	desconectado.emit("o anfitrião saiu")

# --- Conversa entre as máquinas ---------------------------------------------

@rpc("any_peer", "reliable")
func _me_apresento(nome: String) -> void:
	if not sou_anfitriao:
		return
	var id := multiplayer.get_remote_sender_id()
	if jogadores.size() >= MAXIMO_DE_JOGADORES:
		return   # sala cheia
	jogadores[id] = {"nome": nome, "classe": "guerreiro"}
	_manda_lista.rpc(jogadores)
	lista_mudou.emit()

@rpc("authority", "reliable", "call_local")
func _manda_lista(lista: Dictionary) -> void:
	jogadores = lista
	lista_mudou.emit()

# Qualquer um pede a própria classe; quem grava é o anfitrião.
func escolher_classe(classe: String) -> void:
	if sou_anfitriao:
		if jogadores.has(1):
			jogadores[1]["classe"] = classe
		_manda_lista.rpc(jogadores)
		lista_mudou.emit()
	else:
		_peco_classe.rpc_id(1, classe)

@rpc("any_peer", "reliable")
func _peco_classe(classe: String) -> void:
	if not sou_anfitriao:
		return
	var id := multiplayer.get_remote_sender_id()
	if jogadores.has(id):
		jogadores[id]["classe"] = classe
		_manda_lista.rpc(jogadores)
		lista_mudou.emit()

# Só o anfitrião começa a partida.
func comecar_partida() -> void:
	if not sou_anfitriao:
		return
	_comecar.rpc(jogadores)

@rpc("authority", "reliable", "call_local")
func _comecar(lista: Dictionary) -> void:
	jogadores = lista
	em_partida = true
	partida_comecou.emit()
