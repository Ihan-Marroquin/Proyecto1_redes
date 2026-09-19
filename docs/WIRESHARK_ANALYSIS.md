# Análisis de comunicación MCP con Wireshark

Este documento cubre el inciso 9 del proyecto. El objetivo es capturar una sesión
completa entre el cliente del chatbot y el servidor MCP remoto, identificar los mensajes
JSON-RPC y explicar la comunicación en las capas de enlace, red, transporte y
aplicación.

## Escenario reproducible

Para que Wireshark pueda mostrar el cuerpo JSON-RPC sin descifrar TLS, la evidencia
principal se toma contra el mismo servidor Streamable HTTP ejecutado localmente. La
prueba remota en Cloud Run se captura por separado para demostrar que existe tráfico
real hacia la nube; en esa captura HTTPS protege el contenido de aplicación.

### Terminal 1: servidor

```powershell
./run_http.ps1
```

El servidor queda en `http://127.0.0.1:8000/mcp` con el token de demostración
`local-demo-token`. El código, los mensajes MCP y el transporte HTTP son los mismos que
se empaquetan en el contenedor remoto.

### Wireshark

1. Seleccionar **Adapter for loopback traffic capture** en Windows. Si no aparece,
   instalar Npcap con soporte para tráfico loopback.
2. Usar el filtro de captura `tcp port 8000`.
3. Iniciar la captura antes de ejecutar el cliente.

Los filtros de captura de Wireshark emplean la sintaxis de libpcap. La documentación
oficial incluye la forma `tcp port <puerto>`:
<https://www.wireshark.org/docs/wsug_html_chunked/ChCapCaptureFilterSection.html>.

### Terminal 2: cliente

```powershell
$env:MCP_REMOTE_URL = "http://127.0.0.1:8000/mcp"
$env:MCP_AUTH_TOKEN = "local-demo-token"
python -m scripts.verify_remote
```

La salida esperada contiene tres líneas `PASS`: inicialización, lista de herramientas y
llamada a `list_machines`. Al finalizar, detener y guardar la captura como
`docs/evidence/mcp_streamable_http.pcapng`.

> Seguridad: el token local es deliberadamente desechable. No se debe capturar ni
> publicar el token de Cloud Run. Para una captura que se vaya a subir al repositorio,
> usar únicamente `local-demo-token`.

## Filtros de visualización

Los filtros siguientes se aplican después de capturar:

| Propósito | Filtro |
| --- | --- |
| Toda la conversación | `tcp.port == 8000` |
| Solicitudes HTTP | `http.request.method == "POST"` |
| Respuestas HTTP | `http.response.code` |
| Datos con JSON-RPC | `tcp.port == 8000 && tcp.len > 0` |
| Inicio/cierre TCP | `tcp.flags.syn == 1 || tcp.flags.fin == 1 || tcp.flags.reset == 1` |
| Posibles anomalías TCP | `tcp.analysis.flags` |

Si Wireshark no reconoce HTTP en el puerto 8000, seleccionar un paquete, abrir
**Analyze > Decode As...** y asignar `HTTP` al puerto TCP. Para reconstruir cada mensaje,
usar **Analyze > Follow > TCP Stream**. Wireshark permite seguir una conversación desde
el menú contextual de paquetes:
<https://www.wireshark.org/docs/wsug_html_chunked/ChWorkDisplayPopUpSection.html>.

## Clasificación de los mensajes

`scripts.verify_remote` genera esta secuencia determinista. Los números de trama se
completan con la captura realizada, porque cambian entre ejecuciones.

| Orden | Mensaje de aplicación | Tipo JSON-RPC | Papel en MCP | Respuesta esperada |
| --- | --- | --- | --- | --- |
| 1 | `initialize`, `id: 1` | Solicitud | Sincronización y negociación de versión/capacidades | HTTP 200 con `InitializeResult`, el mismo `id: 1` y `MCP-Session-Id` |
| 2 | `notifications/initialized`, sin `id` | Notificación | Fin de sincronización; el cliente anuncia que inicia la fase operativa | HTTP 202 sin cuerpo; no existe respuesta JSON-RPC |
| 3 | `tools/list`, `id: 2` | Solicitud/petición | Descubrimiento de las herramientas disponibles | HTTP 200, respuesta JSON-RPC `id: 2` con seis herramientas |
| 4 | `tools/call`, `id: 3` | Solicitud/petición | Invocación de `list_machines` con `status: warning` | HTTP 200, respuesta JSON-RPC `id: 3` con una máquina |
| 5 | `DELETE /mcp` | Control de transporte HTTP | Cierre explícito de la sesión MCP | HTTP 204 sin cuerpo |

La correlación solicitud-respuesta se hace con `id`. Las notificaciones no llevan `id`
y no reciben respuesta JSON-RPC. El código HTTP 202 únicamente confirma que el
transporte aceptó la notificación.

## Análisis por capas

### Capa de enlace

En la captura loopback, Wireshark puede mostrar un encabezado de la interfaz de captura
en lugar de una trama Ethernet física. No hay un salto por el switch ni resolución ARP
porque ambos procesos están en la misma computadora. En una captura contra Cloud Run,
la dirección MAC de destino observada corresponde al siguiente salto de la red local
(normalmente el gateway), no al servidor remoto. Las direcciones MAC solo tienen
validez dentro del enlace local.

Evidencia a señalar en una trama: tipo de enlace que muestra Wireshark, longitud de la
trama y, cuando exista Ethernet II, MAC origen, MAC destino y EtherType IPv4/IPv6.

### Capa de red

La prueba local utiliza las direcciones loopback del cliente y servidor. IP permite
identificar los extremos lógicos y transportar los segmentos TCP. En la prueba de nube,
la IP destino es la dirección resuelta para el dominio de Cloud Run; los routers cambian
el encabezado de enlace en cada salto, pero conservan las direcciones IP extremo a
extremo salvo traducciones NAT. También se observan TTL/Hop Limit, longitud total y el
campo de protocolo que identifica TCP.

Evidencia a señalar: IP origen, IP destino, versión IP, TTL/Hop Limit y protocolo 6
(TCP).

### Capa de transporte

TCP crea una conexión confiable entre un puerto efímero del cliente y el puerto 8000
del servidor local. Al comienzo se observa el three-way handshake `SYN`, `SYN-ACK`,
`ACK`. Los cuerpos HTTP se dividen en uno o más segmentos, y los números de secuencia y
acuse garantizan entrega ordenada. Al terminar aparecen `FIN/ACK` o, según la
reutilización de conexiones de la biblioteca, cierres separados por solicitud.

El filtro `tcp.analysis.flags` ayuda a encontrar retransmisiones, segmentos fuera de
orden o ventanas agotadas. Wireshark calcula estas observaciones siguiendo el estado de
cada sesión TCP:
<https://www.wireshark.org/docs/wsug_html_chunked/ChAdvTCPAnalysis.html>.

Evidencia a señalar: puertos origen/destino, banderas del establecimiento, `Seq`, `Ack`,
ventana anunciada y ausencia o presencia de retransmisiones.

### Capa de aplicación

Streamable HTTP usa una única ruta `/mcp`. Cada mensaje cliente-servidor se envía con un
`POST` nuevo, `Content-Type: application/json` y un encabezado `Accept` que admite
`application/json` y `text/event-stream`. La respuesta de inicialización crea la sesión
con `MCP-Session-Id`; las solicitudes posteriores incluyen ese valor y
`MCP-Protocol-Version: 2025-11-25`.

Dentro del cuerpo HTTP, JSON-RPC 2.0 aporta `jsonrpc`, `id`, `method`, `params`, `result`
o `error`. MCP define el significado de métodos como `initialize`, `tools/list` y
`tools/call`. La especificación oficial del transporte permite una respuesta JSON o un
flujo SSE para una solicitud, y exige HTTP 202 para notificaciones aceptadas:
<https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>.

## Captura contra Cloud Run

Para evidenciar el servidor realmente remoto, iniciar otra captura sobre el adaptador de
red activo y ejecutar `python -m scripts.verify_remote` con la URL de Cloud Run. Usar el
filtro de visualización `tls || tcp.port == 443`. En esta captura se pueden explicar DNS,
la conexión TCP, el handshake TLS y los registros cifrados. El contenido JSON-RPC no
será visible sin secretos de sesión TLS; esto es el comportamiento de seguridad
esperado. Las capturas del contenido MCP deben provenir de la prueba local controlada.

## Lista de evidencia para el reporte

- Captura del filtro `tcp.port == 8000` con la conversación completa.
- Captura de `initialize` y su respuesta con el mismo `id`.
- Captura de `notifications/initialized` y HTTP 202.
- Captura de `tools/list` y su respuesta.
- Captura de `tools/call` y el resultado de `list_machines`.
- Captura de los detalles de enlace, IP y TCP de una trama representativa.
- Captura remota con DNS/TCP/TLS hacia Cloud Run, sin publicar el token.
- Archivo `.pcapng` sanitizado dentro de `docs/evidence/`.
