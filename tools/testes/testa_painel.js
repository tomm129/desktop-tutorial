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
    ok(JSON.stringify(ctx.store.ativos['esp-01']) === vivoAntes,
       'estado ao vivo intacto (valor critico antigo NAO alarma agora)');

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

console.log();
console.log(falhas === 0 ? 'RESULTADO: todas as verificacoes passaram.'
                         : `RESULTADO: ${falhas} falha(s).`);
process.exit(falhas ? 1 : 0);
