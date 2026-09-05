extends Node
# Atualizador automático do jogo (autoload, roda antes da cena principal).
#
# COMO FUNCIONA
#
# O jogo exportado são dois arquivos: BrawlCoop.exe (o motor, quase nunca muda)
# e BrawlCoop.pck (todo o jogo: scripts, arte, cenas). Uma atualização é só um
# .pck novo — hoje o jogo inteiro tem menos de 5 MB, então não vale a pena
# inventar patch de diferença: baixamos o pacote completo.
#
# O truque para não precisar de instalador nem de um programa separado: em vez
# de sobrescrever arquivos (impossível com o .exe rodando, e chato por causa de
# permissão), o .pck baixado vai para a pasta do usuário e é MONTADO POR CIMA do
# original no _init(), antes da cena principal existir. Como o autoload roda
# antes de tudo, o jogo já sobe com os arquivos novos.
#
#   1. _init()  monta o .pck mais recente que estiver em user://patches/
#   2. _ready() pergunta ao GitHub qual é a última versão
#   3. se houver versão nova, baixa em segundo plano e avisa a cena
#   4. na próxima abertura, o passo 1 aplica sozinho
#
# Se a internet estiver fora, ou o GitHub fora do ar, o jogo abre normalmente na
# versão que já tem — o atualizador nunca bloqueia a abertura.

signal atualizacao_baixada(versao: String)
signal aviso(texto: String)

# Sobe a cada release. É comparada com a do servidor.
const VERSAO := "0.9.1"

# Arquivo de texto com {"versao": "...", "pck": "url", "notas": "..."}
# "releases/latest/download" e resolvido pelo proprio GitHub para a release
# mais nova. Assim nao ha URL para editar a cada versao: basta publicar a
# release com os dois arquivos (versao.json e BrawlCoop.pck) anexados.
const URL_DA_VERSAO := "https://github.com/tomm129/desktop-tutorial/releases/latest/download/versao.json"

const PASTA_DOS_PATCHES := "user://patches"
const TEMPO_LIMITE := 8.0   # segundos esperando o servidor antes de desistir

var versao_em_uso := VERSAO
var _http: HTTPRequest
var _versao_nova := ""
var _url_do_pck := ""

func _init() -> void:
	# Roda ANTES da cena principal: é aqui que uma atualização já baixada entra.
	var pacote := _patch_mais_recente()
	if pacote == "":
		return
	# replace_files = true: os arquivos do patch valem mais que os originais.
	if ProjectSettings.load_resource_pack(pacote, true):
		print("[atualizador] rodando com o patch: ", pacote.get_file())
	else:
		# Patch corrompido (download interrompido, por exemplo): joga fora para
		# não travar o jogo em toda abertura.
		DirAccess.remove_absolute(pacote)
		push_warning("[atualizador] patch invalido, removido: " + pacote)

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = TEMPO_LIMITE
	add_child(_http)
	_http.request_completed.connect(_ao_receber_versao)
	var erro := _http.request(URL_DA_VERSAO)
	if erro != OK:
		aviso.emit("sem conexão para checar atualização")

# --- Passo 2: qual é a última versão? ---------------------------------------

func _ao_receber_versao(_r: int, codigo: int, _h: PackedStringArray, corpo: PackedByteArray) -> void:
	if codigo != 200:
		aviso.emit("não deu para checar atualização (HTTP %d)" % codigo)
		return
	var dados = JSON.parse_string(corpo.get_string_from_utf8())
	if typeof(dados) != TYPE_DICTIONARY or not dados.has("versao"):
		aviso.emit("arquivo de versão do servidor está estranho")
		return

	_versao_nova = str(dados["versao"])
	_url_do_pck = str(dados.get("pck", ""))
	if not _e_mais_nova(_versao_nova, versao_em_uso):
		aviso.emit("você está na versão mais recente (%s)" % versao_em_uso)
		return
	if _url_do_pck == "":
		aviso.emit("versão %s existe, mas sem arquivo para baixar" % _versao_nova)
		return

	aviso.emit("baixando a versão %s..." % _versao_nova)
	_http.request_completed.disconnect(_ao_receber_versao)
	_http.request_completed.connect(_ao_receber_pck)
	if _http.request(_url_do_pck) != OK:
		aviso.emit("não deu para baixar a atualização")

# --- Passo 3: baixa e guarda -------------------------------------------------

func _ao_receber_pck(_r: int, codigo: int, _h: PackedStringArray, corpo: PackedByteArray) -> void:
	if codigo != 200 or corpo.size() == 0:
		aviso.emit("download da atualização falhou (HTTP %d)" % codigo)
		return

	DirAccess.make_dir_recursive_absolute(PASTA_DOS_PATCHES)
	var destino := "%s/BrawlCoop_%s.pck" % [PASTA_DOS_PATCHES, _versao_nova]
	var arquivo := FileAccess.open(destino, FileAccess.WRITE)
	if arquivo == null:
		aviso.emit("não deu para gravar a atualização em disco")
		return
	arquivo.store_buffer(corpo)
	arquivo.close()

	_apaga_patches_antigos(destino)
	atualizacao_baixada.emit(_versao_nova)

# --- Apoio -------------------------------------------------------------------

# Cada .pck é o jogo inteiro, então só o mais novo interessa; os outros só
# ocupariam espaço e ainda correriam o risco de serem montados por engano.
func _apaga_patches_antigos(manter: String) -> void:
	var dir := DirAccess.open(PASTA_DOS_PATCHES)
	if dir == null:
		return
	for nome in dir.get_files():
		var caminho := "%s/%s" % [PASTA_DOS_PATCHES, nome]
		if nome.ends_with(".pck") and caminho != manter:
			DirAccess.remove_absolute(caminho)

func _patch_mais_recente() -> String:
	var dir := DirAccess.open(PASTA_DOS_PATCHES)
	if dir == null:
		return ""
	var melhor := ""
	var melhor_versao := VERSAO
	for nome in dir.get_files():
		if not nome.ends_with(".pck"):
			continue
		var v := nome.trim_prefix("BrawlCoop_").trim_suffix(".pck")
		if _e_mais_nova(v, melhor_versao):
			melhor_versao = v
			melhor = "%s/%s" % [PASTA_DOS_PATCHES, nome]
	if melhor != "":
		versao_em_uso = melhor_versao
	return melhor

# Compara "0.10.2" com "0.9.9" number a number -- comparar como texto diria que
# 0.9.9 e maior, que e o erro classico.
static func _e_mais_nova(candidata: String, atual: String) -> bool:
	var a := candidata.split(".")
	var b := atual.split(".")
	for i in max(a.size(), b.size()):
		var na := int(a[i]) if i < a.size() else 0
		var nb := int(b[i]) if i < b.size() else 0
		if na != nb:
			return na > nb
	return false
