#include "portal.h"
#include "identidade.h"

#include <string.h>
#include <stdlib.h>

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

static const char *TAG = "portal";

#define AP_IP        "192.168.4.1"
#define MAX_REDES    20

static EventGroupHandle_t s_eventos;
#define BIT_SALVO BIT0

static ixnode_config_t s_cfg;

// Redes encontradas na varredura, para o formulário oferecer uma lista em vez
// de exigir que se digite o SSID. Digitar SSID à mão em campo é fonte
// garantida de erro -- maiúscula trocada, espaço no fim -- e o sintoma
// (não conecta) não diz qual foi o engano.
static wifi_ap_record_t s_redes[MAX_REDES];
static uint16_t s_n_redes = 0;

// ---------------------------------------------------------------------------
//  Servidor DNS: responde QUALQUER consulta com o nosso IP.
//
//  É isto que torna o portal CATIVO. Ao entrar numa rede, o celular consulta
//  um domínio conhecido (connectivitycheck.gstatic.com, captive.apple.com…)
//  para testar se há internet. Apontando tudo para cá, ele recebe a nossa
//  página e abre a janela de login sozinho.
//
//  Sem isso o usuário teria de saber que precisa digitar 192.168.4.1 no
//  navegador -- e em campo, com o celular na mão, ninguém sabe.
// ---------------------------------------------------------------------------
typedef struct __attribute__((packed)) {
    uint16_t id;
    uint16_t flags;
    uint16_t qd;      // perguntas
    uint16_t an;      // respostas
    uint16_t ns;
    uint16_t ar;
} dns_cab_t;

static void tarefa_dns(void *arg)
{
    (void)arg;
    int s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s < 0) {
        ESP_LOGE(TAG, "socket DNS falhou");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in meu = {
        .sin_family = AF_INET,
        .sin_port = htons(53),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    if (bind(s, (struct sockaddr *)&meu, sizeof(meu)) < 0) {
        ESP_LOGE(TAG, "bind DNS falhou");
        close(s);
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "DNS respondendo em :53 -> " AP_IP);

    uint8_t buf[512];
    while (1) {
        struct sockaddr_in de;
        socklen_t tam = sizeof(de);
        int n = recvfrom(s, buf, sizeof(buf), 0, (struct sockaddr *)&de, &tam);
        if (n < (int)sizeof(dns_cab_t) + 5) {
            continue;
        }

        dns_cab_t *cab = (dns_cab_t *)buf;
        // Só respondemos a CONSULTA padrão com exatamente uma pergunta.
        if ((ntohs(cab->flags) & 0x8000) || ntohs(cab->qd) != 1) {
            continue;
        }

        // Percorre o nome (rótulos de tamanho prefixado) até o byte zero,
        // para achar onde termina a pergunta.
        int p = sizeof(dns_cab_t);
        while (p < n && buf[p] != 0) {
            p += buf[p] + 1;
        }
        p += 1 + 4;                 // byte zero + QTYPE + QCLASS
        if (p > n || p + 16 > (int)sizeof(buf)) {
            continue;
        }

        cab->flags = htons(0x8180); // resposta, sem erro
        cab->an = htons(1);
        cab->ns = 0;
        cab->ar = 0;

        // Resposta com ponteiro de compressão para o nome da pergunta
        // (0xC00C = offset 12, onde o nome começa).
        uint8_t r[] = {
            0xC0, 0x0C,             // nome comprimido
            0x00, 0x01,             // tipo A
            0x00, 0x01,             // classe IN
            0x00, 0x00, 0x00, 0x0A, // TTL 10s: se o nó sair do ar, o celular
                                    // reconsulta rápido em vez de insistir
            0x00, 0x04,             // tamanho do dado
            192, 168, 4, 1,
        };
        memcpy(buf + p, r, sizeof(r));
        sendto(s, buf, p + sizeof(r), 0, (struct sockaddr *)&de, tam);
    }
}

// ---------------------------------------------------------------------------
//  Página
// ---------------------------------------------------------------------------
static const char PAGINA_TOPO[] =
    "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>iX Node</title><style>"
    "body{font-family:system-ui,-apple-system,sans-serif;background:#111114;"
    "color:#f4f4f5;margin:0;padding:24px;max-width:520px}"
    "h1{font-size:20px;margin:0 0 4px}"
    ".id{color:#71717a;font-size:13px;font-family:ui-monospace,monospace;"
    "margin-bottom:24px}"
    "label{display:block;font-size:13px;color:#a1a1aa;margin:16px 0 6px}"
    "input,select{width:100%;box-sizing:border-box;padding:11px;font-size:16px;"
    "background:#1c1c1f;color:#f4f4f5;border:1px solid #3f3f46;border-radius:8px}"
    "button{width:100%;margin-top:24px;padding:13px;font-size:16px;font-weight:600;"
    "background:#3b82f6;color:#fff;border:0;border-radius:8px}"
    ".dica{color:#71717a;font-size:12px;margin-top:6px}"
    "</style></head><body>"
    "<h1>Configurar iX Node</h1>";

static const char PAGINA_FIM[] =
    "<form method=POST action=/salvar>"
    "<label>Senha do Wi-Fi</label>"
    "<input name=senha type=password placeholder='deixe vazio se a rede for aberta'>"
    "<label>Endereco do gateway (Orange Pi)</label>"
    "<input name=host inputmode=decimal placeholder='ex.: 192.168.0.10' required>"
    "<div class=dica>E o IP onde roda o Mosquitto.</div>"
    "<label>Porta MQTT</label>"
    "<input name=porta inputmode=numeric value=1883>"
    "<button type=submit>Salvar e conectar</button>"
    "</form></body></html>";

static esp_err_t pag_raiz(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_sendstr_chunk(req, PAGINA_TOPO);

    char linha[128];
    snprintf(linha, sizeof(linha), "<div class=id>%s</div>", ixnode_id());
    httpd_resp_sendstr_chunk(req, linha);

    httpd_resp_sendstr_chunk(req, "<label>Rede Wi-Fi</label><select name=ssid form=f>");
    if (s_n_redes == 0) {
        httpd_resp_sendstr_chunk(req, "<option value=''>nenhuma rede encontrada</option>");
    }
    for (uint16_t i = 0; i < s_n_redes; i++) {
        // O RSSI vai junto: com duas redes de mesmo nome (repetidor), é o que
        // permite escolher a que o nó realmente alcança daqui.
        snprintf(linha, sizeof(linha), "<option value=\"%s\">%s (%d dBm)</option>",
                 (char *)s_redes[i].ssid, (char *)s_redes[i].ssid, s_redes[i].rssi);
        httpd_resp_sendstr_chunk(req, linha);
    }
    httpd_resp_sendstr_chunk(req, "</select>");

    httpd_resp_sendstr_chunk(req, PAGINA_FIM);
    httpd_resp_sendstr_chunk(req, NULL);
    return ESP_OK;
}

// Redireciona as sondas de conectividade do sistema operacional para a
// nossa página. Sem isto o Android/iOS marca a rede como "sem internet" e
// alguns telefones a abandonam sozinhos em segundos.
static esp_err_t pag_redirecionar(httpd_req_t *req)
{
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "http://" AP_IP "/");
    httpd_resp_send(req, NULL, 0);
    return ESP_OK;
}

// Decodifica um valor de formulário (application/x-www-form-urlencoded).
static void url_decode(const char *ent, char *saida, size_t max)
{
    size_t j = 0;
    for (size_t i = 0; ent[i] && j + 1 < max; i++) {
        if (ent[i] == '+') {
            saida[j++] = ' ';
        } else if (ent[i] == '%' && ent[i + 1] && ent[i + 2]) {
            char hex[3] = { ent[i + 1], ent[i + 2], 0 };
            saida[j++] = (char)strtol(hex, NULL, 16);
            i += 2;
        } else {
            saida[j++] = ent[i];
        }
    }
    saida[j] = '\0';
}

static void campo(const char *corpo, const char *nome, char *saida, size_t max)
{
    saida[0] = '\0';
    char busca[24];
    snprintf(busca, sizeof(busca), "%s=", nome);

    const char *p = corpo;
    while (p) {
        // Confere que o casamento é início de campo, e não sufixo de outro
        // ("senha=" casaria dentro de "outrasenha=").
        if ((p == corpo || p[-1] == '&') && strncmp(p, busca, strlen(busca)) == 0) {
            p += strlen(busca);
            const char *fim = strchr(p, '&');
            size_t n = fim ? (size_t)(fim - p) : strlen(p);
            if (n >= max) { n = max - 1; }
            char bruto[128];
            if (n >= sizeof(bruto)) { n = sizeof(bruto) - 1; }
            memcpy(bruto, p, n);
            bruto[n] = '\0';
            url_decode(bruto, saida, max);
            return;
        }
        p = strchr(p, '&');
        if (p) { p++; }
    }
}

static esp_err_t pag_salvar(httpd_req_t *req)
{
    char corpo[512];
    int total = req->content_len;
    if (total <= 0 || total >= (int)sizeof(corpo)) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "formulario invalido");
        return ESP_FAIL;
    }

    int lido = 0;
    while (lido < total) {
        int n = httpd_req_recv(req, corpo + lido, total - lido);
        if (n <= 0) {
            httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "leitura falhou");
            return ESP_FAIL;
        }
        lido += n;
    }
    corpo[lido] = '\0';

    ixnode_config_t cfg = {0};
    campo(corpo, "ssid", cfg.ssid, sizeof(cfg.ssid));
    campo(corpo, "senha", cfg.senha, sizeof(cfg.senha));
    campo(corpo, "host", cfg.mqtt_host, sizeof(cfg.mqtt_host));

    char porta[8];
    campo(corpo, "porta", porta, sizeof(porta));
    cfg.mqtt_porta = (porta[0] != '\0') ? atoi(porta) : 1883;
    if (cfg.mqtt_porta <= 0 || cfg.mqtt_porta > 65535) {
        cfg.mqtt_porta = 1883;
    }

    if (cfg.ssid[0] == '\0' || cfg.mqtt_host[0] == '\0') {
        httpd_resp_set_type(req, "text/html; charset=utf-8");
        httpd_resp_sendstr(req,
            "<meta charset=utf-8><body style='font-family:system-ui;background:#111114;"
            "color:#f4f4f5;padding:24px'>Rede e endereco do gateway sao obrigatorios."
            " <a style=color:#3b82f6 href=/>voltar</a></body>");
        return ESP_OK;
    }

    // Grava ANTES de responder. Se a gravação falhar, o usuário precisa saber
    // agora -- responder "salvo" e reiniciar sem ter gravado o traria de volta
    // ao portal sem explicação, e ele repetiria tudo achando que errou.
    if (!ixnode_config_gravar(&cfg)) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            "nao foi possivel gravar na memoria do dispositivo");
        return ESP_FAIL;
    }

    s_cfg = cfg;

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_sendstr(req,
        "<meta charset=utf-8><body style='font-family:system-ui;background:#111114;"
        "color:#f4f4f5;padding:24px'><h2>Configurado</h2>"
        "<p>O no vai reiniciar e conectar na rede escolhida.</p>"
        "<p style=color:#71717a>Esta rede de configuracao vai desaparecer em "
        "instantes — e o sinal de que deu certo.</p></body>");

    xEventGroupSetBits(s_eventos, BIT_SALVO);
    return ESP_OK;
}

static httpd_handle_t subir_http(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.lru_purge_enable = true;
    // As sondas de captive portal batem em caminhos variados; casar por
    // curinga evita registrar um handler por sistema operacional.
    cfg.uri_match_fn = httpd_uri_match_wildcard;

    httpd_handle_t srv = NULL;
    if (httpd_start(&srv, &cfg) != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start falhou");
        return NULL;
    }

    httpd_uri_t raiz = { .uri = "/", .method = HTTP_GET, .handler = pag_raiz };
    httpd_register_uri_handler(srv, &raiz);

    httpd_uri_t salvar = { .uri = "/salvar", .method = HTTP_POST, .handler = pag_salvar };
    httpd_register_uri_handler(srv, &salvar);

    httpd_uri_t resto = { .uri = "/*", .method = HTTP_GET, .handler = pag_redirecionar };
    httpd_register_uri_handler(srv, &resto);

    return srv;
}

// ---------------------------------------------------------------------------
//  Varredura e AP
// ---------------------------------------------------------------------------
static void varrer_redes(void)
{
    // A varredura roda em modo APSTA, ANTES de o AP começar a aceitar
    // clientes: durante o scan o rádio troca de canal, e um celular já
    // conectado veria a rede cair e voltar.
    wifi_scan_config_t sc = { .show_hidden = false };
    if (esp_wifi_scan_start(&sc, true) != ESP_OK) {
        ESP_LOGW(TAG, "varredura falhou; o formulario vem sem lista");
        return;
    }
    s_n_redes = MAX_REDES;
    esp_wifi_scan_get_ap_records(&s_n_redes, s_redes);
    ESP_LOGI(TAG, "%u redes encontradas", s_n_redes);
}

bool ixnode_portal_executar(void)
{
    s_eventos = xEventGroupCreate();

    esp_netif_create_default_wifi_ap();
    esp_netif_create_default_wifi_sta();   // necessário para varrer

    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));

    wifi_config_t ap = {0};
    strlcpy((char *)ap.ap.ssid, ixnode_ap_ssid(), sizeof(ap.ap.ssid));
    ap.ap.ssid_len = strlen(ixnode_ap_ssid());
    ap.ap.max_connection = 2;
    // Rede ABERTA de propósito: uma senha aqui teria de ser conhecida por quem
    // instala, ou seria a mesma em todos os nós -- o que não protege nada e
    // ainda emperra a instalação. A janela de exposição é a de um nó virgem,
    // e o que se pode fazer nela é configurá-lo.
    ap.ap.authmode = WIFI_AUTH_OPEN;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));

    ESP_ERROR_CHECK(esp_wifi_start());

    varrer_redes();

    ESP_LOGI(TAG, "portal no ar: rede '%s', http://" AP_IP "/", ixnode_ap_ssid());

    xTaskCreate(tarefa_dns, "dns_portal", 4096, NULL, 5, NULL);
    httpd_handle_t srv = subir_http();
    if (!srv) {
        return false;
    }

    // Espera indefinidamente. Um nó sem configuração não tem o que fazer
    // além disto, e desistir por tempo só o deixaria inerte até alguém
    // reiniciá-lo na mão.
    xEventGroupWaitBits(s_eventos, BIT_SALVO, pdTRUE, pdTRUE, portMAX_DELAY);

    // Um instante para o navegador receber a página de confirmação antes de
    // o rádio cair.
    vTaskDelay(pdMS_TO_TICKS(1500));
    httpd_stop(srv);
    return true;
}
