#pragma once

// Identidade do nó — derivada do HARDWARE, nunca de configuração.
//
// Isto existe para que exista UMA firmware, igual em toda unidade que sai da
// bancada. Um DEVICE_ID em config.h obrigaria a compilar uma imagem por nó:
// vinte nós, vinte builds, e um erro de digitação vira dois dispositivos com
// o mesmo id publicando no mesmo tópico — que o painel lê como um só,
// alternando entre duas máquinas.
//
// O MAC do rádio é único de fábrica e imutável. Os três últimos bytes dão
// 16,7 milhões de combinações, o que é folga suficiente para uma planta.

#define IXNODE_ID_MAX 16   // "ixn-a1b2c3" + terminador, com sobra

// Devolve o identificador no formato "ixn-a1b2c3". Estável entre reboots e
// entre regravações do firmware. Seguro para chamar antes do Wi-Fi subir.
const char *ixnode_id(void);

// Nome do ponto de acesso do portal: "iX-Node-a1b2c3".
//
// Traz o mesmo sufixo do id de propósito: com vários nós novos ligados ao
// mesmo tempo, é ele que diz qual rede é qual — e bate com a etiqueta do
// invólucro, para não haver dúvida na hora de instalar.
const char *ixnode_ap_ssid(void);
