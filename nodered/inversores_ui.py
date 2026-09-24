"""Menu Inversores do painel: o validador compartilhado e a tela.

Fica fora do gera_flow.py pelo tamanho, como o marca.py. O gera_flow importa
daqui e injeta:

  * VALIDADOR_JS  -- no no que GRAVA (servidor) e na TELA (aviso ao digitar).
    O mesmo codigo nos dois lugares: a tela nunca aceita o que o servidor
    recusaria, e vice-versa.
  * TELA          -- o ui-template (Vue) da pagina Inversores.

As regras espelham a validar() do servico em Python
(integracoes/inversores/servico_inversores.py). Os dois lados leem os mesmos
casos de tools/testes/casos_validacao_inversores.json -- se divergirem, um
dos testes quebra.

O catalogo de modelos entra como a constante CATALOGO, injetada pelo
gera_flow a partir de integracoes/inversores/catalogo.json.
"""

VALIDADOR_JS = r"""
// ===== validador de inversores (gerado: nodered/inversores_ui.py) =====
// Espelho de validar() do servico em Python. Casos compartilhados em
// tools/testes/casos_validacao_inversores.json.
function _ipValido(v) {
    if (typeof v !== 'string') { return false; }
    const p = v.split('.');
    // String(+x) === x recusa zero a esquerda ("010"), como o Python.
    return p.length === 4 && p.every(function (x) {
        return /^\d{1,3}$/.test(x) && +x <= 255 && String(+x) === x;
    });
}
function _inteiro(v, mn, mx) {
    return typeof v === 'number' && Number.isInteger(v) && v >= mn && v <= mx;
}
function _padrao(v, d) { return (v === undefined || v === null || v === '') ? d : v; }

// Os campos chegam do formulario como TEXTO. Converte o que e numero,
// segundo o catalogo -- sem isto "1" e 1 seriam enderecos diferentes e o
// conflito de endereco passaria despercebido.
function normalizarItem(it) {
    const r = JSON.parse(JSON.stringify(it || {}));
    const c = r.conexao || {};
    const tipo = CATALOGO.conexoes[c.tipo];
    if (tipo) {
        tipo.campos.forEach(function (f) {
            const v = c[f.id];
            const numerico = f.tipo === 'inteiro' ||
                (f.tipo === 'escolha' && f.opcoes && typeof f.opcoes[0].valor === 'number');
            if (numerico && typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v))) {
                c[f.id] = Number(v);
            }
            if (typeof c[f.id] === 'string') { c[f.id] = c[f.id].trim(); }
        });
    }
    r.conexao = c;
    ['nome', 'tag'].forEach(function (k) {
        if (typeof r[k] === 'string') { r[k] = r[k].trim(); }
    });
    if (r.intervalo_s === '' || r.intervalo_s === null) { delete r.intervalo_s; }
    else if (r.intervalo_s !== undefined) { r.intervalo_s = Number(r.intervalo_s); }
    return r;
}

function slugInversor(t) {
    return String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30);
}

// id estavel: e ele que o cadastro de ativos usa para associar o drive, entao
// nasce uma vez e nunca muda -- trocar o nome ou a tag depois nao o afeta.
function gerarIdInversor(lista, tag, nome, modelo) {
    const base = 'inv-' + (slugInversor(tag) || slugInversor(nome) || slugInversor(modelo) || 'drive');
    const usados = {};
    (lista || []).forEach(function (i) { usados[i.id] = true; });
    if (!usados[base]) { return base; }
    for (let n = 2; ; n++) {
        if (!usados[base + '-' + n]) { return base + '-' + n; }
    }
}

function validarInversores(config) {
    const modelos = CATALOGO.modelos;
    const itens = (config && config.inversores) || [];
    const validos = [], erros = [];
    const ids = {}, posicoes = {}, barramentos = {};

    itens.forEach(function (it, n) {
        const iid = String((it && it.id) || ('item ' + (n + 1)));
        const erro = function (m) { erros.push({ id: iid, erro: m }); };
        if (!it || typeof it !== 'object' || !it.id) { erro('sem id'); return; }
        if (it.habilitado === false) { return; }
        if (ids[iid]) { erro('id repetido'); return; }
        const m = modelos[it.modelo];
        if (!m) { erro("modelo desconhecido: '" + it.modelo + "'"); return; }
        const c = it.conexao || {};
        const tipo = c.tipo;
        if (m.conexoes.indexOf(tipo) < 0) {
            erro(m.nome + " não se conecta por '" + tipo + "' (aceita: " + m.conexoes.join(', ') + ')');
            return;
        }
        let chave, desc, ps, ajuste;
        if (tipo === 'cip') {
            const pos = _padrao(c.posicao, 0);
            if (!_ipValido(c.ip)) { erro("IP inválido: '" + c.ip + "'"); return; }
            if (!_inteiro(pos, 0, 4)) { erro('posição no nó tem de ser 0 a 4, veio ' + pos); return; }
            if (pos && !m.multidrive) { erro(m.nome + ' não tem Multi-Drive: posição tem de ser 0'); return; }
            chave = ['cip', c.ip, _padrao(c.porta, 44818), pos].join('|');
            desc = c.ip + ' posição ' + pos;
        } else if (tipo === 'tcp') {
            if (!_ipValido(c.ip)) { erro("IP inválido: '" + c.ip + "'"); return; }
            if (!_inteiro(_padrao(c.porta, 502), 1, 65535)) { erro('porta TCP inválida'); return; }
            if (!_inteiro(_padrao(c.endereco, 1), 1, 247)) { erro('endereço de escravo tem de ser 1 a 247'); return; }
            chave = ['tcp', c.ip, _padrao(c.porta, 502), _padrao(c.endereco, 1)].join('|');
            desc = c.ip + ' endereço ' + _padrao(c.endereco, 1);
        } else {
            ps = String(c.porta_serial || '').trim();
            if (!ps) { erro('porta serial vazia'); return; }
            if (!_inteiro(c.endereco, 1, 247)) { erro('endereço de escravo tem de ser 1 a 247'); return; }
            if ([9600, 19200, 38400].indexOf(_padrao(c.baud, 9600)) < 0) { erro('velocidade tem de ser 9600, 19200 ou 38400'); return; }
            if (['E', 'O', 'N'].indexOf(_padrao(c.paridade, 'E')) < 0) { erro('paridade tem de ser E, O ou N'); return; }
            ajuste = [_padrao(c.baud, 9600), _padrao(c.paridade, 'E')];
            const b = barramentos[ps];
            if (b && (b.ajuste[0] !== ajuste[0] || b.ajuste[1] !== ajuste[1])) {
                erro(ps + ' já está em ' + b.ajuste[0] + ' ' + b.ajuste[1] + ' (por causa de ' + b.id +
                     '); todos os drives de um barramento têm de usar a mesma velocidade e paridade');
                return;
            }
            chave = ['rtu', ps, c.endereco].join('|');
            desc = ps + ' endereço ' + c.endereco;
        }
        if (posicoes[chave]) { erro(desc + ' já é usado por ' + posicoes[chave]); return; }
        if (tipo === 'rtu' && !barramentos[ps]) { barramentos[ps] = { ajuste: ajuste, id: iid }; }
        ids[iid] = true;
        posicoes[chave] = iid;
        validos.push(it);
    });
    return { validos: validos, erros: erros };
}

// Onde o drive esta, em uma linha: para a lista e para as mensagens.
function descreverConexao(it) {
    const c = (it && it.conexao) || {};
    if (c.tipo === 'cip') {
        const pos = _padrao(c.posicao, 0);
        return c.ip + (pos ? '  ·  drive ' + pos + ' (DSI)' : '  ·  drive 0 (Ethernet)');
    }
    if (c.tipo === 'tcp') { return c.ip + ':' + _padrao(c.porta, 502) + '  ·  endereço ' + _padrao(c.endereco, 1); }
    if (c.tipo === 'rtu') {
        return c.porta_serial + '  ·  endereço ' + c.endereco + '  ·  ' + _padrao(c.baud, 9600) + ' ' + _padrao(c.paridade, 'E');
    }
    return '';
}
// ===== fim do validador =====
"""


# =====================================================================
#  A tela (ui-template, Vue). __CATALOGO__ e __VALIDADOR__ sao trocados
#  pelo gera_flow na geracao.
# =====================================================================
TELA = r"""
<template>
<div class="inv">
    <div class="topo">
        <div>
            <h2>Inversores</h2>
            <p class="ajuda">
                Cadastre aqui os inversores que o gateway deve ler. Escolha o
                modelo e o formulário pede só o que ele precisa. O gateway
                aplica sozinho, em segundos — sem editar arquivo nem reiniciar
                nada. O gateway <b>só lê</b>: nada daqui escreve no drive.
            </p>
        </div>
        <div class="gw" :class="gwClasse" :title="gwTitulo">
            <span class="ponto"></span>{{ gwTexto }}
        </div>
    </div>

    <!-- ---------------- lista ---------------- -->
    <div v-if="!lista.length && !aberto" class="vazio">
        Nenhum inversor cadastrado. Comece por <b>Adicionar inversor</b>.
    </div>

    <table v-if="lista.length" class="lista">
        <tr class="cab">
            <td>Inversor</td><td>Modelo</td><td>Conexão</td><td>Leitura</td><td></td>
        </tr>
        <tr v-for="i in lista" :key="i.id" :class="{ off: i.habilitado === false, sel: editId === i.id }">
            <td>
                <div class="nome">{{ i.nome || '(sem nome)' }}
                    <span v-if="i.tag" class="tagi">{{ i.tag }}</span></div>
                <div class="sub">{{ i.id }}
                    <span v-if="i.associado" class="ass">· {{ i.associado }}</span>
                    <a v-else class="ass pend" href="/dashboard/cadastro">· não associado a um ativo</a>
                </div>
            </td>
            <td><div>{{ nomeModelo(i.modelo) }}</div><div class="sub">{{ marcaModelo(i.modelo) }}</div></td>
            <td class="con">{{ i.conexao_desc }}</td>
            <td>
                <div class="estado" :class="i.estado">
                    <span class="ponto"></span>{{ i.estado_texto }}
                </div>
                <div v-if="i.leitura" class="sub num">{{ i.leitura }}</div>
                <div v-if="i.erro" class="err-linha">{{ i.erro }}</div>
            </td>
            <td>
                <div class="acoes">
                    <button class="mini" @click="editar(i)">editar</button>
                    <button class="mini" @click="alternar(i)">{{ i.habilitado === false ? 'ligar' : 'desligar' }}</button>
                    <button class="mini perigo" @click="remover(i)">
                        {{ confirmar === i.id ? 'confirmar?' : 'remover' }}</button>
                </div>
            </td>
        </tr>
    </table>

    <div v-if="!aberto" class="botoes">
        <button class="ok" @click="novo()">+ Adicionar inversor</button>
    </div>
    <div v-if="aviso" class="aviso" :class="{ ruim: avisoRuim }">{{ aviso }}</div>

    <!-- ---------------- formulario ---------------- -->
    <div v-if="aberto" class="form">
        <div class="titulo">{{ editId ? 'Editar ' + (f.nome || editId) : 'Adicionar inversor' }}</div>

        <div class="linha">
            <label>Modelo</label>
            <select v-model="f.modelo" @change="trocouModelo()">
                <option value="" disabled>escolha…</option>
                <optgroup v-for="g in porMarca" :key="g.marca" :label="g.marca">
                    <option v-for="m in g.modelos" :key="m.id" :value="m.id">{{ m.nome }}</option>
                </optgroup>
            </select>
        </div>
        <div v-if="modelo" class="nota">{{ modelo.descricao }}</div>

        <div v-if="modelo && modelo.conexoes.length > 1" class="linha">
            <label>Conexão</label>
            <div class="seg">
                <button v-for="t in modelo.conexoes" :key="t" :class="{ on: f.tipo === t }"
                        @click="trocarTipo(t)">{{ rotuloConexao(t) }}</button>
            </div>
        </div>

        <template v-if="f.tipo">
            <template v-for="c in campos" :key="c.id">
                <div class="linha">
                    <label>{{ c.rotulo }}</label>
                    <select v-if="c.tipo === 'escolha'" v-model="f.c[c.id]" @change="mexeu()">
                        <option v-for="o in c.opcoes" :key="o.valor" :value="o.valor">{{ o.rotulo }}</option>
                    </select>
                    <input v-else v-model="f.c[c.id]" @input="mexeu()"
                           :inputmode="c.tipo === 'inteiro' || c.tipo === 'ip' ? 'decimal' : 'text'"
                           :placeholder="c.tipo === 'ip' ? 'ex.: 192.168.1.20' : (c.padrao !== undefined ? String(c.padrao) : '')">
                </div>
                <div v-if="c.ajuda" class="nota">{{ c.ajuda }}</div>
            </template>
            <div v-if="barramentoAviso" class="nota info">{{ barramentoAviso }}</div>
        </template>

        <div class="linha">
            <label>Nome</label>
            <input v-model="f.nome" @input="mexeu()" placeholder="ex.: Exaustor da linha 1">
        </div>
        <div class="linha">
            <label>Tag no painel</label>
            <input v-model="f.tag" @input="mexeu()" placeholder="ex.: U11" style="max-width: 140px">
        </div>
        <div class="linha">
            <label>Leitura</label>
            <label class="chk"><input type="checkbox" v-model="f.habilitado" @change="mexeu()"> ligada</label>
        </div>

        <div v-if="tocado && errosItem.length" class="erros">
            <div v-for="(e, k) in errosItem" :key="k">✕ {{ e }}</div>
        </div>
        <div v-for="(a, k) in avisosItem" :key="'w' + k" class="nota info">{{ a }}</div>

        <div class="botoes">
            <button class="ok" :disabled="!podeSalvar" @click="salvar()">
                {{ salvando ? 'salvando…' : (editId ? 'Salvar alterações' : 'Adicionar') }}</button>
            <button class="cancelar" @click="cancelar()">Cancelar</button>
        </div>
    </div>
</div>
</template>

<script>
export default {
    data () {
        // O Dashboard 2.0 so aceita o OBJETO do componente neste <script>:
        // codigo antes do "export default" quebra a tela inteira com
        // "Unexpected token 'export'". Por isso o catalogo e o validador
        // sao montados aqui, a cada abertura da tela, num objeto da pagina.
        window.InsightXInv = (function () {
            const CATALOGO = __CATALOGO__;
            __VALIDADOR__
            return { CATALOGO: CATALOGO, normalizarItem: normalizarItem,
                     gerarIdInversor: gerarIdInversor, validarInversores: validarInversores,
                     descreverConexao: descreverConexao };
        })();
        return {
            lista: [], gw: null,
            aberto: false, editId: null, tocado: false, salvando: false,
            f: { modelo: '', tipo: '', c: {}, nome: '', tag: '', habilitado: true },
            aviso: '', avisoRuim: false, confirmar: null, pedido: 0
        }
    },
    computed: {
        porMarca () {
            const g = {};
            Object.keys(window.InsightXInv.CATALOGO.modelos).forEach(function (id) {
                const m = window.InsightXInv.CATALOGO.modelos[id];
                (g[m.marca] = g[m.marca] || []).push({ id: id, nome: m.nome });
            });
            return Object.keys(g).sort().map(function (k) { return { marca: k, modelos: g[k] }; });
        },
        modelo () { return window.InsightXInv.CATALOGO.modelos[this.f.modelo] || null; },
        campos () { return (window.InsightXInv.CATALOGO.conexoes[this.f.tipo] || { campos: [] }).campos; },
        outros () { const e = this.editId; return this.lista.filter(function (i) { return i.id !== e; }); },
        item () {
            const conexao = Object.assign({ tipo: this.f.tipo }, this.f.c);
            return window.InsightXInv.normalizarItem({
                id: this.editId || window.InsightXInv.gerarIdInversor(this.outros, this.f.tag, this.f.nome, this.f.modelo),
                modelo: this.f.modelo, nome: this.f.nome, tag: this.f.tag,
                habilitado: this.f.habilitado, conexao: conexao
            });
        },
        errosItem () {
            if (!this.f.modelo) { return ['escolha o modelo']; }
            if (!this.f.tipo) { return ['escolha a conexão']; }
            const it = this.item;
            if (it.habilitado === false) { return []; }
            const r = window.InsightXInv.validarInversores({ inversores: this.outros.concat([it]) });
            return r.erros.filter(function (e) { return e.id === it.id; }).map(function (e) { return e.erro; });
        },
        avisosItem () {
            const it = this.item, c = it.conexao || {};
            const av = [];
            if (c.tipo === 'cip' && c.posicao > 0 &&
                !this.outros.some(function (o) { return o.conexao && o.conexao.tipo === 'cip' &&
                                                  o.conexao.ip === c.ip && !(o.conexao.posicao > 0); })) {
                av.push('Nenhum drive na posição 0 deste IP está cadastrado. Tudo bem se ele não for ' +
                        'monitorado — mas é por ele que os encadeados são alcançados.');
            }
            return av;
        },
        barramentoAviso () {
            const c = this.f.c;
            if (this.f.tipo !== 'rtu' || !c.porta_serial) { return ''; }
            const ps = String(c.porta_serial).trim();
            const vizinhos = this.outros.filter(function (o) {
                return o.conexao && o.conexao.tipo === 'rtu' && o.conexao.porta_serial === ps;
            });
            if (!vizinhos.length) { return ''; }
            return 'Este barramento já tem ' + vizinhos.length + ' drive(s): ' +
                vizinhos.map(function (v) { return (v.tag || v.nome || v.id) + ' (end. ' + v.conexao.endereco + ')'; }).join(', ') +
                '. Use um endereço livre; a velocidade e a paridade já vieram iguais às dele.';
        },
        podeSalvar () { return !this.salvando && this.errosItem.length === 0; },
        gwClasse () {
            if (!this.gw || !this.gw.recebido) { return 'nada'; }
            if (this.gw.erro_arquivo) { return 'ruim'; }
            return 'bom';
        },
        gwTexto () {
            if (!this.gw || !this.gw.recebido) { return 'gateway ainda não respondeu'; }
            if (this.gw.erro_arquivo) { return 'gateway não conseguiu ler a lista'; }
            return 'gateway aplicou ' + this.gw.quando;
        },
        gwTitulo () { return this.gw && this.gw.erro_arquivo ? this.gw.erro_arquivo : ''; }
    },
    methods: {
        nomeModelo (id) { const m = window.InsightXInv.CATALOGO.modelos[id]; return m ? m.nome : id; },
        marcaModelo (id) { const m = window.InsightXInv.CATALOGO.modelos[id]; return m ? m.marca : ''; },
        rotuloConexao (t) { return (window.InsightXInv.CATALOGO.conexoes[t] || {}).rotulo || t; },
        padroes (tipo) {
            const c = {};
            ((window.InsightXInv.CATALOGO.conexoes[tipo] || {}).campos || []).forEach(function (f) {
                if (f.padrao !== undefined) { c[f.id] = f.padrao; }
            });
            return c;
        },
        novo () {
            this.editId = null; this.tocado = false; this.aviso = '';
            this.f = { modelo: '', tipo: '', c: {}, nome: '', tag: '', habilitado: true };
            this.aberto = true;
        },
        editar (i) {
            this.editId = i.id; this.tocado = true; this.aviso = '';
            const c = Object.assign({}, i.conexao || {}); const tipo = c.tipo; delete c.tipo;
            this.f = { modelo: i.modelo, tipo: tipo, c: Object.assign(this.padroes(tipo), c),
                       nome: i.nome || '', tag: i.tag || '', habilitado: i.habilitado !== false };
            this.aberto = true;
        },
        trocouModelo () {
            const m = this.modelo;
            this.trocarTipo(m && m.conexoes.indexOf(this.f.tipo) >= 0 ? this.f.tipo : (m ? m.conexoes[0] : ''));
        },
        trocarTipo (t) {
            this.f.tipo = t;
            this.f.c = this.padroes(t);
            this.mexeu();
        },
        mexeu () {
            this.tocado = true;
            // RS-485: ao escolher um barramento que ja existe, herda a
            // velocidade e a paridade dele -- o erro mais facil de cometer
            // vira o mais dificil.
            const c = this.f.c;
            if (this.f.tipo === 'rtu' && c.porta_serial) {
                const ps = String(c.porta_serial).trim();
                const v = this.outros.find(function (o) {
                    return o.conexao && o.conexao.tipo === 'rtu' && o.conexao.porta_serial === ps;
                });
                if (v) { c.baud = v.conexao.baud || 9600; c.paridade = v.conexao.paridade || 'E'; }
            }
        },
        cancelar () { this.aberto = false; this.editId = null; },
        salvar () {
            this.tocado = true;
            if (!this.podeSalvar) { return; }
            this.salvando = true; this.pedido += 1;
            this.send({ payload: { acao: 'salvar', item: this.item, original: this.editId, pedido: this.pedido } });
        },
        alternar (i) {
            this.pedido += 1;
            this.send({ payload: { acao: 'habilitar', id: i.id, habilitado: i.habilitado === false, pedido: this.pedido } });
        },
        remover (i) {
            // Duas etapas, sem dialogo do navegador: o primeiro clique arma,
            // o segundo (em ate 4 s) confirma.
            if (this.confirmar !== i.id) {
                this.confirmar = i.id;
                const self = this;
                setTimeout(function () { if (self.confirmar === i.id) { self.confirmar = null; } }, 4000);
                return;
            }
            this.confirmar = null; this.pedido += 1;
            this.send({ payload: { acao: 'remover', id: i.id, pedido: this.pedido } });
        }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) {
                const p = (m && m.payload) || {};
                if (p.lista) { this.lista = p.lista; this.gw = p.gateway || null; }
                if (p.resposta && p.resposta.pedido === this.pedido) {
                    this.salvando = false;
                    this.aviso = p.resposta.texto; this.avisoRuim = !p.resposta.ok;
                    if (p.resposta.ok) { this.aberto = false; this.editId = null; }
                }
            }
        }
    }
}
</script>

<style scoped>
.inv   { color: #a1a1aa; font-size: 14px; }
.topo  { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
h2     { color: #f4f4f5; font-size: 22px; margin: 0 0 4px; font-weight: 600; }
.ajuda { color: #71717a; font-size: 13px; margin: 0 0 20px; max-width: 72ch; line-height: 1.45; }
.ajuda b { color: #a1a1aa; }
.gw    { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; border: 1px solid #3f3f46;
         border-radius: 999px; padding: 5px 12px; white-space: nowrap; }
.ponto { width: 8px; height: 8px; border-radius: 50%; background: #52525b; flex: none; }
.gw.bom .ponto  { background: #22c55e; }
.gw.ruim        { color: #ef4444; border-color: #7f1d1d; }
.gw.ruim .ponto { background: #ef4444; }

.vazio { color: #52525b; font-size: 13px; border: 1px dashed #3f3f46; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
table.lista { border-collapse: collapse; width: 100%; margin-bottom: 14px; }
.lista td  { padding: 10px 12px; border-bottom: 1px solid #27272a; vertical-align: top; }
.lista .cab td { font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: #52525b; padding-top: 0; }
.lista tr.off td { opacity: .55; }
.lista tr.sel td { background: #1d2a3a; }
.nome  { color: #f4f4f5; }
.sub   { color: #71717a; font-size: 12px; margin-top: 3px; }
.num   { font-variant-numeric: tabular-nums; }
.con   { color: #a1a1aa; font-size: 13px; }
.ass   { color: #71717a; }
.ass.pend { color: #f59e0b; text-decoration: none; }
.ass.pend:hover { text-decoration: underline; }
.tagi  { color: #f59e0b; font-size: 11px; border: 1px solid #f59e0b; border-radius: 8px; padding: 0 6px; margin-left: 6px; }
.estado { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; }
.estado.lendo .ponto      { background: #22c55e; }
.estado.sem_resposta      { color: #ef4444; }
.estado.sem_resposta .ponto, .estado.recusado .ponto { background: #ef4444; }
.estado.recusado          { color: #ef4444; }
.estado.aguardando .ponto { background: #f59e0b; }
.err-linha { color: #ef4444; font-size: 12px; margin-top: 4px; max-width: 42ch; }
.acoes { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; }
.acoes .mini { min-width: 72px; text-align: center; }

.form  { background: #151518; border: 1px solid #3f3f46; border-radius: 10px; padding: 18px; }
.titulo { font-size: 12px; text-transform: uppercase; letter-spacing: .4px; color: #a1a1aa; margin-bottom: 14px; }
.linha { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
label  { width: 220px; color: #71717a; font-size: 13px; flex: none; }
label.chk { width: auto; color: #a1a1aa; display: inline-flex; gap: 8px; align-items: center; }
input, select {
    background: #0b0b0c; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 6px;
    padding: 8px 12px; font-size: 14px; flex: 1; max-width: 420px; font-family: inherit;
}
input[type=checkbox] { flex: none; width: 16px; height: 16px; accent-color: #3987e5; }
input:focus, select:focus { outline: none; border-color: #3987e5; }
.nota  { color: #71717a; font-size: 12px; margin: -4px 0 12px 232px; max-width: 64ch; line-height: 1.4; }
.nota.info { color: #a1a1aa; }
.seg   { display: inline-flex; border: 1px solid #3f3f46; border-radius: 6px; overflow: hidden; }
.seg button { background: transparent; color: #a1a1aa; border: none; border-radius: 0; padding: 8px 14px; }
.seg button.on { background: #1d2a3a; color: #f4f4f5; }
.erros { color: #ef4444; font-size: 13px; margin: 6px 0 4px 232px; line-height: 1.6; }

.botoes { display: flex; gap: 10px; margin-top: 16px; }
button  { border: none; border-radius: 6px; padding: 10px 20px; font-size: 14px; cursor: pointer;
          font-family: inherit; transition: filter .15s ease; }
button:hover { filter: brightness(1.1); }
.ok       { background: #3987e5; color: #ffffff; }
.ok:disabled { background: #27272a; color: #52525b; cursor: not-allowed; filter: none; }
.cancelar { background: transparent; color: #a1a1aa; border: 1px solid #3f3f46; }
.mini     { background: transparent; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 11px;
            padding: 4px 10px; border-radius: 6px; }
.mini:hover { color: #f4f4f5; border-color: #52525b; filter: none; }
.mini.perigo:hover { color: #ef4444; border-color: #ef4444; }
.aviso     { color: #22c55e; font-size: 13px; margin: 4px 0 12px; }
.aviso.ruim { color: #ef4444; }
@media (max-width: 700px) {
    .linha { flex-direction: column; align-items: stretch; }
    label  { width: auto; }
    .nota, .erros { margin-left: 0; }
}
</style>
"""
