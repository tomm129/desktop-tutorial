---
name: insightx-provisionamento-primeiro-boot
description: "InsightX ESP32 nodes are provisioned on first boot via the captive portal (iX Node firmware), never via config.h"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 6b704974-8695-4705-b65c-572c31486d6e
  modified: 2026-09-24T19:11:07.998Z
---

InsightX field nodes must be configured on FIRST BOOT through the captive portal (network, gateway, MQTT credentials, node name) and load it from NVS on every reboot after. Do not propose or prepare `config.h` builds (firmware/esp32-campo is legacy) for new nodes or bench tests.

**Why:** the user agreed this long ago to minimize manual action; it is part of the "config pela interface, quase zero edição de arquivo" goal ([[insightx-config-pela-interface]]). On 2026-09-24 I started preparing a config.h for a bench test and the user corrected me.

**How to apply:** for any ESP32 flashing/bench test, use firmware/ixnode-provisionamento (ESP-IDF). If the board is not the C6 devkit, adapt pins/LED per board instead of falling back to the Arduino config.h firmware.
