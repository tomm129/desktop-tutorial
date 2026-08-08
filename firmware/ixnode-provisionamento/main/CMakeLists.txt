idf_component_register(
    SRCS "main.c" "identidade.c" "config_nvs.c" "portal.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_netif esp_event esp_http_server mqtt lwip esp_timer
)
