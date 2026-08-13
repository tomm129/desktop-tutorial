idf_component_register(
    SRCS "main.c" "identidade.c" "config_nvs.c" "portal.c"
         "vibracao.c" "adxl345.c" "led_ident.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_netif esp_event esp_http_server mqtt lwip esp_timer
             esp_driver_i2c esp_driver_gpio json
)
