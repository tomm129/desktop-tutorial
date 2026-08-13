# Compila a MESMA vibracao.c do firmware -- nao uma copia. Uma copia
# divergiria em silencio, que e exatamente a falha que este teste existe
# para pegar.
set(FW "${CMAKE_CURRENT_LIST_DIR}/../../../../firmware/ixnode-provisionamento/main")

idf_component_register(
    SRCS "teste_main.c" "${FW}/vibracao.c"
    INCLUDE_DIRS "." "${FW}"
)
