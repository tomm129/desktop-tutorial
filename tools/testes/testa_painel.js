// Roda o codigo REAL dos nos do flows.json contra mensagens simuladas.
// Nao e leitura de codigo: executa e confere o resultado.
const fs = require('fs');

const flow = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const acharNo = (nome) => {
    const n = flow.find(x => x.name === nome && typeof x.func === 'string');
    if (!n) throw new Error(`no "${nome}" nao encontrado`);
    return n;
};

// --- Contexto de flow simulado --------------------------------------
function novoCtx() {
    const store = {};
    return {
        flow: { get: (k) => store[k], set: (k, v) => { store[k] = v; } },
        store,
        node: { warn: () => {}, error: (e) => { throw e; } }
    };
}

function rodar(no, msg, ctx) {
    const fn = new Function('msg', 'node', 'flow', 'global', 'context',
                            'RED', 'env', 'Buffer', no.func);
    return fn(msg, ctx.node, ctx.flow, {}, {}, {}, {}, Buffer);
}

let falhas = 0;
function ok(cond, nome, extra) {
    if (!cond) falhas++;
    console.log(`  [${cond ? 'OK ' : 'FALHA'}] ${nome}${extra ? '  ' + extra : ''}`);
}

const reg = acharNo('registrar telemetria');
const cmd = acharNo('monta comando');

// =====================================================================
console.log('\n=== 1. Amostra ao vivo com os campos novos ===');
{
    const ctx = novoCtx();
    rodar(reg, { payload: {
        device_id: 'esp-01', ts: 1000, temperatura_c: 45.2,
        vibracao: { rms_g: 0.31, pico_g: 1.2, crista: 3.9,
                    vel_mm_s: 2.15, fs_hz: 368.4 }
    }}, ctx);

    const a = ctx.store.ativos['esp-01'];
    ok(a.vib_vel_mm_s === 2.15, 'velocidade guardada', `= ${a.vib_vel_mm_s}`);
    ok(a.vib_crista === 3.9, 'crista guardada', `= ${a.vib_crista}`);
    ok(a.hist.vel.length === 1 && a.hist.crista.length === 1,
       'series de tendencia alimentadas');
    const acc = ctx.store.acumulador['esp-01'];
    ok(acc.vel.n === 1 && acc.vel.soma === 2.15, 'acumulador de velocidade');
    ok(acc.crista.n === 1, 'acumulador de crista');
}

// =====================================================================
console.log('\n=== 2. Firmware ANTIGO (sem vel/crista) nao pode alarmar ===');
{
    const ctx = novoCtx();
    rodar(reg, { payload: {
        device_id: 'esp-velho', ts: 1000, temperatura_c: 44.0,
        vibracao: { rms_g: 0.28, pico_g: 1.0, fs_hz: 370 }
    }}, ctx);

    const a = ctx.store.ativos['esp-velho'];
    // undefined = "nao tem esse sensor" (ignorado no calculo de estado)
    // null      = "tem e falhou"       (vira ATENCAO)
    ok(a.vib_vel_mm_s === undefined, 'velocidade ausente vira undefined, nao null',
       `= ${String(a.vib_vel_mm_s)}`);
    ok(a.vib_crista === undefined, 'crista ausente vira undefined, nao null',
       `= ${String(a.vib_crista)}`);
    ok(a.vib_rms_g === 0.28, 'o que existe continua chegando');
}

// =====================================================================
console.log('\n=== 3. Backfill nao encosta no estado ao vivo ===');
{
    const ctx = novoCtx();
    // Primeiro uma leitura ao vivo, boa.
    rodar(reg, { payload: { device_id: 'esp-01', temperatura_c: 40.0,
        vibracao: { rms_g: 0.2, pico_g: 0.8, crista: 3.5, vel_mm_s: 1.5, fs_hz: 370 }
    }}, ctx);
    const vivoAntes = JSON.stringify(ctx.store.ativos['esp-01']);

    // Agora um backfill CRITICO de 2 horas atras.
    const saida = rodar(reg, { payload: {
        device_id: 'esp-01', buffer: true, atraso_ms: 7200000,
        temperatura_c: 95.0,
        vibracao: { rms_g: 3.0, pico_g: 9.0, crista: 7.5, vel_mm_s: 12.0, fs_hz: 370 }
    }}, ctx);

    ok(saida === null, 'backfill nao emite mensagem para grafico ao vivo');
    // Compara tudo MENOS 'visto_em'. A versao anterior comparava o objeto
    // inteiro e falhava de forma INTERMITENTE: 'visto_em' e Date.now(), e o
    // teste so passava quando as duas mensagens caiam no mesmo
    // milissegundo. E o backfill atualizar 'visto_em' e correto -- e prova
    // de vida do dispositivo (ver o comentario no gera_flow.py).
    const semVisto = (o) => { const c = Object.assign({}, o); delete c.visto_em;
                              return JSON.stringify(c); };
    ok(semVisto(ctx.store.ativos['esp-01']) === semVisto(JSON.parse(vivoAntes)),
       'valores ao vivo intactos (valor critico antigo NAO alarma agora)');
    ok(ctx.store.ativos['esp-01'].visto_em >= JSON.parse(vivoAntes).visto_em,
       'backfill conta como sinal de vida (nao marca o dispositivo como mudo)');

    const fila = ctx.store.backfill;
    ok(fila && fila.length === 1, 'amostra foi para a fila de backfill');
    const idade = Date.now() - fila[0].ts;
    ok(Math.abs(idade - 7200000) < 2000, 'timestamp reconstruido de atraso_ms',
       `idade = ${Math.round(idade / 60000)} min`);
    ok(fila[0].vib_vel_mm_s === 12.0, 'valores do backfill preservados');

    const faixas = ctx.store.recuperacoes['esp-01'];
    ok(Array.isArray(faixas) && faixas.length === 1, 'faixa de recuperacao criada');
}

// =====================================================================
console.log('\n=== 4. Duas quedas distantes viram faixas SEPARADAS ===');
{
    const ctx = novoCtx();
    const bf = (atraso) => rodar(reg, { payload: {
        device_id: 'esp-01', buffer: true, atraso_ms: atraso,
        temperatura_c: 50, vibracao: { rms_g: 0.3, pico_g: 1, crista: 3, vel_mm_s: 2, fs_hz: 370 }
    }}, ctx);

    // Queda A: ~2h atras, tres amostras proximas entre si
    bf(7200000); bf(7195000); bf(7190000);
    // Queda B: ~20 min atras -- separada por muito mais que 5 min
    bf(1200000); bf(1195000);

    const faixas = ctx.store.recuperacoes['esp-01'];
    ok(faixas.length === 2, 'duas faixas distintas', `= ${faixas.length}`);
    if (faixas.length === 2) {
        ok(faixas[0].n === 3 && faixas[1].n === 2, 'amostras contadas por faixa',
           `= ${faixas[0].n} e ${faixas[1].n}`);
        const dur0 = (faixas[0].ate - faixas[0].de) / 1000;
        ok(dur0 < 60, 'faixa antiga nao engoliu a recente', `dur = ${dur0}s`);
    }
    ok(ctx.store.backfill.length === 5, 'todas as amostras na fila');
}

// =====================================================================
console.log('\n=== 5. Valores impossiveis sao rejeitados ===');
{
    const ctx = novoCtx();
    rodar(reg, { payload: { device_id: 'esp-01', temperatura_c: 45,
        vibracao: { rms_g: 0.3, pico_g: 1, crista: 0.5, vel_mm_s: 999, fs_hz: 370 }
    }}, ctx);
    const a = ctx.store.ativos['esp-01'];
    ok(a.vib_vel_mm_s === null, 'velocidade de 999 mm/s rejeitada');
    ok(a.vib_crista === null, 'crista de 0,5 rejeitada (impossivel por definicao)');
}

// =====================================================================
console.log('\n=== 6. Teto da fila de backfill ===');
{
    const ctx = novoCtx();
    for (let i = 0; i < 2100; i++) {
        rodar(reg, { payload: { device_id: 'esp-' + (i % 9), buffer: true,
            atraso_ms: 1000 + i * 10, temperatura_c: 50,
            vibracao: { rms_g: 0.3, pico_g: 1, crista: 3, vel_mm_s: 2, fs_hz: 370 }
        }}, ctx);
    }
    ok(ctx.store.backfill.length === 2000, 'fila limitada a 2000',
       `= ${ctx.store.backfill.length}`);
}

// =====================================================================
// Classificacao ISO 20816-3 / 10816-1.
//
// Estes numeros vao para a tela como "ZONA C" e disparam alarme. Errar o
// GRUPO e pior que nao ter a medida: rotula maquina boa como ruim, ou
// (o caso perigoso) maquina degradando como aceitavel.
//
// Valores conferidos contra o texto da ISO 20816-3:2022, Tabelas A.1 e A.2.
console.log('\n=== 7. Grupo ISO derivado da plaqueta ===');
{
    const painel = flow.find(n => typeof n.func === 'string'
                                  && n.func.includes('const ISO_ZONAS'));
    if (!painel) {
        ok(false, 'no do painel encontrado');
    } else {
        // Extrai so as definicoes de que precisamos e avalia isoladas.
        const ini = painel.func.indexOf('const ISO_ZONAS');
        const fim = painel.func.indexOf('function limites_de');
        const trecho = painel.func.slice(ini, fim);
        // O trecho tambem carrega o bloco de histerese, que le o contexto do
        // flow; um stub basta, nada aqui depende dele.
        const api = new Function('flow', 'node', trecho +
            '\n return { ISO_ZONAS, grupo_iso, zona_iso, altura_eixo };')(
            { get: () => ({}), set: () => {} }, { warn: () => {} });

        ok(api.altura_eixo('132S/M') === 132, 'carcaca 132S/M -> H=132 mm');
        ok(api.altura_eixo('112M') === 112, 'carcaca 112M -> H=112 mm');
        ok(api.altura_eixo(undefined) === 0, 'carcaca ausente -> 0');

        const casos = [
            [{ potencia_cv: 10, carcaca: '132S/M' }, 'peq',
             'motor de 10 CV / carcaca 132 -> fora do escopo da 20816-3'],
            [{ potencia_kw: 30, carcaca: '200L' }, '2r', '30 kW -> Grupo 2'],
            [{ potencia_kw: 400 }, '1r', '400 kW -> Grupo 1'],
            [{ carcaca: '355M' }, '1r', 'so a carcaca 355 ja da Grupo 1'],
            [{ carcaca: '180M' }, '2r', 'carcaca 180 -> Grupo 2'],
            [{ potencia_kw: 30, iso_grupo: '2f' }, '2f',
             'iso_grupo explicito vence a derivacao'],
            [{}, '2r', 'placa vazia -> padrao'],
        ];
        for (const [placa, esperado, nome] of casos) {
            const obtido = api.grupo_iso(placa);
            ok(obtido === esperado, nome, `-> ${obtido}`);
        }

        // Confere as tabelas contra a norma.
        const tab = { '2r': [1.4, 2.8, 4.5], '2f': [2.3, 4.5, 7.1],
                      '1r': [2.3, 4.5, 7.1], '1f': [3.5, 7.1, 11.0],
                      'peq': [0.71, 1.8, 4.5] };
        for (const g of Object.keys(tab)) {
            const z = api.ISO_ZONAS[g];
            const bate = z && z.ab === tab[g][0] && z.bc === tab[g][1]
                           && z.cd === tab[g][2];
            ok(bate, `tabela ${g} = ${tab[g].join(' / ')} mm/s`);
        }

        // O caso que motivou tudo: o MESMO valor cai em zonas diferentes
        // conforme o porte da maquina.
        ok(api.zona_iso(2.0, '2r') === 'B',
           '2,0 mm/s num motor medio -> zona B (aceitavel)');
        ok(api.zona_iso(2.0, 'peq') === 'C',
           '2,0 mm/s num motor pequeno -> zona C (acao necessaria)');
        ok(api.zona_iso(0.5, 'peq') === 'A', '0,5 mm/s pequeno -> zona A');
        ok(api.zona_iso(12.0, '1f') === 'D', '12 mm/s Grupo 1 flexivel -> zona D');
    }
}

// =====================================================================
// Separador de dias na linha do tempo.
//
// So aparece quando a janela cruza meia-noite, e a janela cresce com a
// idade do evento mais antigo (teto de 24h). Ou seja: numa instalacao
// recem-ligada ele NUNCA aparece, e um erro aqui ficaria escondido por
// dias antes de alguem notar. Por isso o teste forja um evento antigo.
console.log('\n=== 8. Linha do tempo: viradas de dia ===');
{
    const painel = flow.find(n => n.name === 'montar painel'
                                  && typeof n.func === 'string');
    if (!painel) {
        ok(false, 'no "montar painel" encontrado');
    } else {
        const rodarPainel = (horasAtras) => {
            const agora = Date.now();
            const inicio = agora - horasAtras * 3600000;
            const store = {
                historico_alarmes: [{
                    chave: 'Teste', ativo: 'Teste', parte: null,
                    estado: 'critico', motivos: ['prova'],
                    inicio_ms: inicio, fim_ms: inicio + 600000
                }],
                // Sem ao menos um ativo a funcao retorna cedo, com 5 saidas
                // em vez de 10, e o m10 nem chega a existir.
                ativos: { 'esp-teste': {
                    id: 'esp-teste', tipo: 'esp32', visto_em: agora,
                    temperatura_c: 45, vib_rms_g: 0.2, vib_vel_mm_s: 1.1,
                    vib_crista: 3.5, conexao: 'online',
                    hist: { temp: [45], vib: [0.2], vel: [1.1], crista: [3.5] }
                } },
                cadastro: {}, estados_por_device: {}, lacunas: [],
                recuperacoes: {}, niveis_anteriores: {}, acumulador: {},
                eventos_gravados: {}, ativos_existentes: []
            };
            const fn = new Function('msg', 'node', 'flow', 'global', 'context',
                                    'RED', 'env', 'Buffer', painel.func);
            const saidas = fn({ payload: {}, topic: '' },
                { warn: () => {}, error: () => {}, status: () => {} },
                { get: (k) => store[k], set: (k, v) => { store[k] = v; } },
                { get: () => undefined, set: () => {} },
                { get: () => undefined, set: () => {} },
                {}, { get: () => undefined }, Buffer);
            // Acha a saida pelo NO de destino, nao por posicao.
            //
            // Antes era saidas[saidas.length - 1], assumindo que a linha do
            // tempo fosse sempre a ultima. Bastou o painel ganhar mais uma
            // saida para o teste ler outra coisa e quebrar num ponto que
            // nada tinha a ver com a mudanca.
            const idx = painel.wires.findIndex(
                (w) => Array.isArray(w) && w.includes('linha_tempo'));
            if (idx < 0) { return null; }
            const m10 = saidas[idx];
            return m10 && m10.payload ? m10.payload : null;
        };

        const curto = rodarPainel(0.1);
        ok(curto && Array.isArray(curto.dias), 'payload traz o array dias');
        ok(curto && curto.dias.length === 0,
           'janela de minutos nao desenha virada nenhuma',
           curto ? `-> ${curto.dias.length}` : '');

        const longo = rodarPainel(23);
        if (!longo) {
            ok(false, 'm10 produzido na janela longa');
        } else {
            ok(longo.dias.length === 1, 'janela de 24h cruza exatamente 1 meia-noite',
               `-> ${longo.dias.length}`);
            if (longo.dias.length) {
                const d = longo.dias[0];
                const agora = new Date();
                ok(d.pct >= 0 && d.pct <= 100, 'pct dentro de 0-100',
                   `-> ${d.pct.toFixed(1)}`);
                ok(/^\d{2}\/\d{2}$/.test(d.rot), 'rotulo no formato DD/MM',
                   `-> ${d.rot}`);
                // A posicao tem de corresponder a hora atual: quanto mais
                // tarde do dia, mais para a esquerda fica a meia-noite.
                const min = agora.getHours() * 60 + agora.getMinutes();
                const esperado = 100 * (1 - min / 1440);
                ok(Math.abs(d.pct - esperado) < 6, 'pct bate com a hora do dia',
                   `-> ${d.pct.toFixed(1)} vs ~${esperado.toFixed(1)}`);
                const hoje = ('0' + agora.getDate()).slice(-2) + '/' +
                             ('0' + (agora.getMonth() + 1)).slice(-2);
                ok(d.rot === hoje, 'rotulo e a data da virada cruzada',
                   `-> ${d.rot}`);
            }
        }
    }
}

// =====================================================================
// Comandos para o ativo aberto: confirmacao em dois cliques do reinicio.
//
// Reiniciar um ESP32 e destrutivo, entao o botao arma no primeiro clique
// e so executa no segundo clique dentro de 5 s. Erros de temporizacao aqui
// deixariam o operador sem feedback ou derrubariam modulos acidentalmente.
console.log('\n=== 9. Comando reiniciar: confirmacao em dois cliques ===');
{
    function rodarCmd(payload, store) {
        const ctx = { flow: { get: (k) => store[k], set: (k, v) => { store[k] = v; } },
                      node: { warn: () => {}, error: (e) => { throw e; } } };
        return rodar(cmd, { payload }, ctx);
    }

    function novoStore() {
        return {
            ativo_sel: 'motor-01',
            esp32_por_chave: { 'motor-01': ['esp-a', 'esp-b'] }
        };
    }

    // 1. Primeiro clique: arma, avisa e NAO envia comando MQTT.
    {
        const store = novoStore();
        const [mqtt, aviso] = rodarCmd('reiniciar', store);
        ok(mqtt === null, 'primeiro clique nao emite MQTT',
           mqtt ? `-> ${JSON.stringify(mqtt)}` : '');
        ok(aviso && /clique de novo/i.test(aviso.payload),
           'primeiro clique pede confirmacao', aviso ? `-> ${aviso.payload}` : '');
        ok(typeof store.reinicio_armado === 'number' && store.reinicio_armado > 0,
           'reinicio_armado registrado', `-> ${store.reinicio_armado}`);
    }

    // 2. Segundo clique dentro de 5 s: envia reiniciar para todos os modulos.
    {
        const store = novoStore();
        store.reinicio_armado = Date.now() - 1000; // armado ha 1 s
        const [mqtt, aviso] = rodarCmd('reiniciar', store);
        ok(Array.isArray(mqtt) && mqtt.length === 2,
           'segundo clique envia para todos os modulos', `-> ${mqtt.length}`);
        if (mqtt.length === 2) {
            ok(mqtt.every(m => m.topic === 'monitoramento/esp-a/cmd'
                             || m.topic === 'monitoramento/esp-b/cmd'),
               'topicos apontam para os device_ids do ativo');
            ok(mqtt.every(m => m.payload === JSON.stringify({ comando: 'reiniciar' })),
               'payload e comando de reiniciar');
        }
        ok(store.reinicio_armado === 0,
           'reinicio_armado e zerado apos a execucao');
        ok(aviso && /reiniciando/i.test(aviso.payload),
           'avisa que esta reiniciando', aviso ? `-> ${aviso.payload}` : '');
    }

    // 3. Segundo clique depois de 5 s: trata como primeiro clique.
    {
        const store = novoStore();
        store.reinicio_armado = Date.now() - 6000; // armado ha 6 s
        const [mqtt, aviso] = rodarCmd('reiniciar', store);
        ok(mqtt === null, 'clique apos 5 s nao emite MQTT (rearma)',
           mqtt ? `-> ${JSON.stringify(mqtt)}` : '');
        ok(aviso && /clique de novo/i.test(aviso.payload),
           'clique apos 5 s pede confirmacao de novo');
        ok(typeof store.reinicio_armado === 'number' && store.reinicio_armado > 0,
           'reinicio_armado e atualizado no rearme');
    }
}

// =====================================================================
console.log('\n=== Multi-Drive: a origem do inversor chega ao cadastro ===');
{
    const regCorr = acharNo('registrar corrente');
    const montar = acharNo('montar painel');
    const ctx = novoCtx();
    const pub = (id, origem) => rodar(regCorr, { topic: `monitoramento/${id}/inversor`,
        payload: { corrente_a: 7.8, frequencia_hz: 40, falha: { codigo: 0 }, origem } }, ctx);

    pub('u11', { no: '192.168.1.20', drive: 0, nome: 'Exaustor 1', tag: 'U11' });
    pub('u12', { no: '192.168.1.20', drive: 1, nome: 'Exaustor 2', tag: 'U12' });
    pub('d3', { barramento: '/dev/ttyUSB0', endereco: 3, modelo: 'danfoss_fc51',
                nome: 'Bomba', tag: 'D3' });
    // entradas ruins vindas da rede nao podem quebrar a tela
    pub('lixo1', { no: '10.0.0.9', drive: 7, nome: 'x'.repeat(200) });
    pub('lixo2', 'nao sou objeto');
    const A = ctx.store.ativos;
    ok(A.u12.origem && A.u12.origem.drive === 1 && A.u12.origem.tag === 'U12',
       'registrar corrente guarda a origem', `-> ${JSON.stringify(A.u12.origem)}`);
    ok(A.lixo1.origem.drive === null && A.lixo1.origem.nome.length === 60,
       'drive fora de 0..4 vira null e nome longo e cortado');
    ok(A.lixo2.origem === undefined, 'origem que nao e objeto e ignorada');

    rodar(montar, { payload: Date.now() },
          Object.assign(ctx, { node: { warn: () => {}, error: (e) => { throw e; },
                                       send: () => {}, status: () => {} } }));
    const pend = ctx.store.nao_atribuidos || [];
    const p12 = pend.find(d => d.id === 'u12'), p11 = pend.find(d => d.id === 'u11');
    ok(p12 && p12.origem === '192.168.1.20  ·  drive 1 (DSI)  ·  Exaustor 2',
       'pendente mostra IP, posicao no no e nome', `-> ${p12 && p12.origem}`);
    ok(p11 && /drive 0 \(Ethernet\)/.test(p11.origem), 'drive 0 aparece como o da Ethernet');
    ok(p12 && p12.tag_sugerida === 'U12', 'tag do arquivo do sidecar vem sugerida');
    const pd3 = pend.find(d => d.id === 'd3');
    ok(pd3 && pd3.origem === '/dev/ttyUSB0  ·  endereço 3  ·  VLT Micro Drive FC 51  ·  Bomba',
       'Danfoss no RS-485: barramento, endereco e o NOME do modelo (do catalogo)',
       `-> ${pd3 && pd3.origem}`);
}
// =====================================================================
console.log('\n=== Graficos do Detalhe: so as partes do ativo aberto ===');
{
    // Bug achado na revisao: o Detalhe da "Caldeira" mostrava as curvas da
    // planta inteira, porque recebia o mesmo fluxo da pagina Tendencias.
    const regCorr = acharNo('registrar corrente');
    const montar = acharNo('montar painel');
    const abrir = acharNo('abrir detalhe');
    const ctx = novoCtx();
    ctx.node.send = () => {}; ctx.node.status = () => {};
    ctx.store.cadastro = {
        Caldeira: { partes: { Bomba: { esp32: 'esp-cb', inversor: 'inv-cb' },
                              Vent:  { esp32: 'esp-cv' } } },
        Torre: { esp32: 'esp-t', inversor: 'inv-t' }
    };
    const tel = (id) => rodar(reg, { payload: { device_id: id, temperatura_c: 50,
                                                 vibracao: { rms_g: 0.2 } } }, ctx);
    const cor = (id) => rodar(regCorr, { topic: `monitoramento/${id}/inversor`,
                                         payload: { corrente_a: 9, falha: { codigo: 0 } } }, ctx);
    ['esp-cb', 'esp-cv', 'esp-t'].forEach(tel); ['inv-cb', 'inv-t'].forEach(cor);
    rodar(montar, { payload: Date.now() }, ctx);   // elege os da Tendencias

    const [nav, limpa] = rodar(abrir, { payload: 'Caldeira' }, ctx);
    ok(nav.payload.page === 'Detalhe', 'abrir ainda navega para o Detalhe');
    ok(Array.isArray(limpa.payload) && limpa.payload.length === 0,
       'ao abrir, os graficos do Detalhe sao limpos (o ui-chart acumula series)');
    ok(JSON.stringify(ctx.store.devices_detalhe) === '["esp-cb","esp-cv","inv-cb"]',
       'recorte = ESP32 e inversores das partes da Caldeira',
       `-> ${JSON.stringify(ctx.store.devices_detalhe)}`);

    const r1 = tel('esp-cb'), r2 = tel('esp-t');
    ok(r1[2] && r1[3] && r1[2].topic === 'esp-cb', 'parte da Caldeira chega aos graficos do Detalhe');
    ok(r2[2] === null && r2[3] === null, 'a Torre NAO chega aos graficos do Detalhe da Caldeira');
    ok(r2[0] && r2[0].topic === 'esp-t', '...mas continua na pagina Tendencias');
    const c1 = cor('inv-cb'), c2 = cor('inv-t');
    ok(c1[1] && c1[1].topic === 'inv-cb' && c2[1] === null,
       'corrente: so o inversor da Caldeira vai ao Detalhe');
    ok(c2[0] && c2[0].topic === 'inv-t', 'corrente da Torre continua na Tendencias');

    rodar(abrir, { payload: 'Torre' }, ctx);
    ok(tel('esp-t')[2] !== null && tel('esp-cb')[2] === null,
       'trocar de ativo troca o recorte');
}
// =====================================================================
console.log('\n=== Menu Inversores: o servidor do painel ===');
{
    const aplicar = acharNo('aplicar inversores');
    const montarInv = acharNo('montar tela de inversores');
    // Estes nos usam env.get (caminho do arquivo); o rodar() comum passa {}.
    const rodarEnv = (no, msg, ctx) => {
        const fn = new Function('msg', 'node', 'flow', 'global', 'context',
                                'RED', 'env', 'Buffer', no.func);
        return fn(msg, ctx.node, ctx.flow, {}, {}, {}, { get: () => undefined }, Buffer);
    };
    const casos = JSON.parse(fs.readFileSync(
        require('path').join(__dirname, 'casos_validacao_inversores.json'), 'utf8')).casos;

    // 1. Os MESMOS casos que o validador do servico (Python) le.
    let iguais = 0;
    for (const c of casos) {
        const ctx = novoCtx();
        const [, r] = rodarEnv(aplicar, { payload: { acao: 'validar', inversores: c.inversores } }, ctx);
        const v = r.payload.validacao;
        const ids = v.validos.map(x => x.id);
        const erros = Object.fromEntries(v.erros.map(x => [x.id, x.erro]));
        const bate = JSON.stringify(ids) === JSON.stringify(c.validos) &&
            Object.keys(erros).length === Object.keys(c.erros).length &&
            Object.entries(c.erros).every(([id, t]) => (erros[id] || '').includes(t));
        if (bate) { iguais++; } else { ok(false, 'caso compartilhado: ' + c.caso, JSON.stringify(v.erros)); }
    }
    ok(iguais === casos.length, `validador do painel bate com os ${casos.length} casos compartilhados com o Python`,
       `-> ${iguais}/${casos.length}`);

    // 2. Salvar: id gerado, arquivo gravado.
    const ctx = novoCtx();
    const pf = (pos, extra) => Object.assign({ modelo: 'pf525', nome: 'Exaustor', tag: 'U1' + pos,
        habilitado: true, conexao: { tipo: 'cip', ip: '192.168.1.20', posicao: String(pos) } }, extra || {});
    let [arq, r, redesenho] = rodarEnv(aplicar, { payload: { acao: 'salvar', item: pf(0), pedido: 1 } }, ctx);
    ok(r.payload.resposta.ok && r.payload.resposta.pedido === 1, 'salvar responde ok para o mesmo pedido');
    ok(arq && /inversores\.json$/.test(arq.filename), 'grava inversores.json', `-> ${arq && arq.filename}`);
    ok(redesenho, 'e manda redesenhar a tela na hora');
    const gravado = JSON.parse(arq.payload).inversores;
    ok(gravado.length === 1 && gravado[0].id === 'inv-u10', 'id gerado da tag', `-> ${gravado[0].id}`);
    ok(gravado[0].conexao.posicao === 0,
       'posicao que veio como TEXTO do formulario e gravada como NUMERO');

    // 3. Conflito: recusado, e NADA e gravado.
    [arq, r] = rodarEnv(aplicar, { payload: { acao: 'salvar', item: pf(0, { tag: 'U99' }), pedido: 2 } }, ctx);
    ok(!r.payload.resposta.ok && /usado por inv-u10/.test(r.payload.resposta.texto) && arq === null,
       'mesmo drive de novo: recusado com o motivo, sem gravar', `-> ${r.payload.resposta.texto}`);

    // 4. Editar mantem o id (o cadastro de ativos depende dele) e o intervalo.
    ctx.store.inversores_cfg[0].intervalo_s = 7;
    [arq, r] = rodarEnv(aplicar, { payload: { acao: 'salvar', original: 'inv-u10', pedido: 3,
        item: pf(0, { id: 'inv-outro', tag: 'NOVA', nome: 'Exaustor renomeado' }) } }, ctx);
    const ed = JSON.parse(arq.payload).inversores[0];
    ok(ed.id === 'inv-u10' && ed.tag === 'NOVA', 'editar troca a tag mas NAO o id', `-> ${ed.id}`);
    ok(ed.intervalo_s === 7, 'campo que a tela nao edita sobrevive a edicao');

    // 5. Desligar e religar num lugar ocupado.
    rodarEnv(aplicar, { payload: { acao: 'habilitar', id: 'inv-u10', habilitado: false, pedido: 4 } }, ctx);
    [arq, r] = rodarEnv(aplicar, { payload: { acao: 'salvar', item: pf(0, { tag: 'U77' }), pedido: 5 } }, ctx);
    ok(r.payload.resposta.ok, 'com o primeiro desligado, outro pode ocupar o lugar');
    [arq, r] = rodarEnv(aplicar, { payload: { acao: 'habilitar', id: 'inv-u10', habilitado: true, pedido: 6 } }, ctx);
    ok(!r.payload.resposta.ok && arq === null, 'religar num lugar ocupado e recusado, sem gravar',
       `-> ${r.payload.resposta.texto}`);

    // 5b. Editar um drive do COMECO da lista para o lugar de outro: o
    // conflito tem de cair nele, nao no vizinho que ja funcionava.
    {
        const c3 = novoCtx();
        c3.store.inversores_cfg = [
            { id: 'p', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.1', posicao: 0 } },
            { id: 'q', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.1', posicao: 1 } }];
        const [a3, r3] = rodarEnv(aplicar, { payload: { acao: 'salvar', original: 'p', pedido: 1,
            item: { modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.1', posicao: 1 } } } }, c3);
        ok(!r3.payload.resposta.ok && a3 === null && /usado por q/.test(r3.payload.resposta.texto),
           'editar o primeiro para o lugar do segundo: recusa o EDITADO, nao o vizinho',
           `-> ${r3.payload.resposta.texto}`);
    }

    // 6. Remover um drive associado avisa onde ele continua.
    ctx.store.cadastro = { 'Caldeira 01': { partes: { 'Exaustor': { inversor: 'inv-u77' } } } };
    [arq, r] = rodarEnv(aplicar, { payload: { acao: 'remover', id: 'inv-u77', pedido: 7 } }, ctx);
    ok(r.payload.resposta.ok && /Caldeira 01 › Exaustor/.test(r.payload.resposta.texto),
       'remover avisa que ele continua associado a um ativo', `-> ${r.payload.resposta.texto}`);

    // 7. A lista mostra o estado de cada um, juntando config, gateway e leitura.
    const c2 = novoCtx();
    const agora = Date.now();
    c2.store.inversores_cfg = [
        { id: 'a', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.1', posicao: 0 } },
        { id: 'b', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.1', posicao: 1 } },
        { id: 'c', modelo: 'danfoss_fc51', conexao: { tipo: 'rtu', porta_serial: '/dev/ttyUSB0', endereco: 1 } },
        { id: 'd', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.2', posicao: 0 } },
        { id: 'e', modelo: 'pf525', habilitado: false, conexao: { tipo: 'cip', ip: '10.0.0.3', posicao: 0 } },
    ];
    c2.store.ativos = { a: { visto_em: agora - 2000, corrente_a: 12.34, frequencia_hz: 45.6 },
                        b: { visto_em: agora - 90000, conexao: 'offline' } };
    c2.store.inversores_estado = { ts: agora - 5000, ativos: ['a', 'b', 'c'],
                                   erros: [{ id: 'd', erro: 'IP inválido' }] };
    c2.store.cadastro = { 'Caldeira 01': { partes: { 'Bomba': { inversor: 'a' } } } };
    const tela = rodarEnv(montarInv, { payload: 1 }, c2).payload;
    const est = Object.fromEntries(tela.lista.map(i => [i.id, i.estado]));
    ok(est.a === 'lendo' && est.b === 'sem_resposta' && est.c === 'aguardando' &&
       est.d === 'recusado' && est.e === 'desligado',
       'cinco estados: lendo, sem resposta, aguardando, recusado, desligado', `-> ${JSON.stringify(est)}`);
    const la = tela.lista.find(i => i.id === 'a');
    ok(la.leitura === '12,34 A  ·  45,6 Hz' && la.associado === 'Caldeira 01 › Bomba',
       'leitura em pt-BR e o ativo associado', `-> ${la.leitura} | ${la.associado}`);
    ok(tela.lista.find(i => i.id === 'b').conexao_desc === '10.0.0.1  ·  drive 1 (DSI)',
       'conexao descrita em uma linha');
    // Recem-cadastrado, com um 'offline' retido de antes: aguardando, nao vermelho.
    c2.store.inversores_cfg.push({ id: 'novo', modelo: 'pf525', conexao: { tipo: 'cip', ip: '10.0.0.7', posicao: 0 } });
    c2.store.ativos.novo = { conexao: 'offline', visto_em: agora - 600000 };
    const t2 = rodarEnv(montarInv, { payload: 1 }, c2).payload;
    ok(t2.lista.find(i => i.id === 'novo').estado === 'aguardando',
       "recem-cadastrado com 'offline' retido de antes: 'aguardando', nao 'sem resposta'");
    ok(tela.gateway.recebido && /há 5 s/.test(tela.gateway.quando), 'mostra quando o gateway aplicou',
       `-> ${tela.gateway.quando}`);
}
console.log();
console.log(falhas === 0 ? 'RESULTADO: todas as verificacoes passaram.'
                         : `RESULTADO: ${falhas} falha(s).`);
process.exit(falhas ? 1 : 0);
