# Guía de la Entrega 1

## Alcance confirmado por el catedrático

Para el reporte de la Entrega 1 únicamente corresponden los siguientes incisos:

| Inciso | Evidencia en el proyecto |
| --- | --- |
| 8. Especificación, parámetros y puntos de interacción | Sección “Especificación del servidor local” y `docs/Reporte_Entrega_1.pdf` |
| 10. Conclusiones y comentario sobre el proyecto | Sección final de `docs/Reporte_Entrega_1.pdf` |

El inciso 9, correspondiente al análisis con Wireshark, se agrega hasta la segunda
entrega junto con el servidor remoto. Canvas solicita una URL, por lo que se debe subir
el repositorio privado con el reporte PDF incluido y entregar el enlace del repositorio.

El código conserva la implementación completa del chatbot y de los servidores locales,
pero el reporte de esta entrega se limita a los incisos 8 y 10.

## Caso de uso propuesto

El servidor representa una herramienta básica de gestión de mantenimiento industrial.
El chatbot puede consultar el estado de maquinaria, revisar la disponibilidad de
repuestos y administrar órdenes de trabajo. El ejemplo se centra en una pequeña planta
de bebidas con una selladora, una bomba sanitaria y un compresor.

Este caso resulta apropiado porque un técnico normalmente consulta información que se
encuentra separada entre registros de maquinaria, inventario y órdenes de mantenimiento.
El agente actúa como una interfaz conversacional, pero las acciones que cambian datos
siempre requieren confirmación del usuario.

### Mensaje corto para solicitar aprobación

> Buenos días, ingeniero. Para el servidor MCP local propongo un caso de gestión de
> mantenimiento industrial. El servidor permitiría consultar el estado de máquinas,
> revisar existencias de repuestos y crear o cerrar órdenes de trabajo. La demostración
> se realizaría con maquinaria de una planta de bebidas y las acciones que modifiquen
> información requerirían confirmación del usuario. ¿Podría confirmarme si el caso es
> adecuado para el proyecto?

## Especificación del servidor local

### Datos generales

| Elemento | Valor |
| --- | --- |
| Nombre | `industrial-maintenance-server` |
| Versión del servidor | `1.0.0` |
| Versión MCP | `2025-11-25` |
| Formato | JSON-RPC 2.0 |
| Transporte | stdio |
| Delimitación | Un objeto JSON por línea, codificado en UTF-8 |
| Persistencia | `data/maintenance.json` |

Al ser un servidor local por stdio, no posee endpoints HTTP. Sus puntos de interacción
son los métodos MCP `initialize`, `notifications/initialized`, `ping`, `tools/list` y
`tools/call`.

### Herramientas y parámetros

#### `list_machines`

Lista la maquinaria registrada.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `status` | string | No | `operational`, `warning`, `stopped` o `maintenance` |

Ejemplo de uso: “Lista las máquinas que tienen una advertencia”.

#### `get_machine_status`

Devuelve el registro completo de una máquina.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `machine_id` | string | Sí | Identificador como `SELL-01` |

Ejemplo: “Muéstrame el estado de la selladora SELL-01”.

#### `list_work_orders`

Consulta órdenes de mantenimiento.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `machine_id` | string | No | Filtra por máquina |
| `status` | string | No | `open` o `closed` |

#### `check_spare_part`

Busca repuestos y calcula si se recomienda reabastecer.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `query` | string | Sí | Número de parte, nombre o máquina compatible |

#### `create_work_order`

Crea una orden y la guarda en el archivo de datos.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `machine_id` | string | Sí | Máquina registrada |
| `issue` | string | Sí | Descripción del problema, mínimo 5 caracteres |
| `priority` | string | Sí | `low`, `medium`, `high` o `critical` |

Esta acción requiere confirmación en la consola.

#### `close_work_order`

Cierra una orden abierta y registra la solución.

| Parámetro | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `work_order_id` | string | Sí | Identificador como `WO-0001` |
| `resolution` | string | Sí | Trabajo realizado, mínimo 5 caracteres |

Esta acción requiere confirmación en la consola.

## Ejemplos JSON-RPC

### Inicialización

Solicitud del cliente:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"cc3067-manual-mcp-chatbot","version":"1.0.0"}}}
```

Notificación posterior:

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

### Descubrimiento de herramientas

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

### Consulta de una máquina

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_machine_status","arguments":{"machine_id":"SELL-01"}}}
```

### Creación de una orden

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"create_work_order","arguments":{"machine_id":"SELL-01","issue":"Inspect sealing resistance terminals","priority":"high"}}}
```

## Cómo ejecutar la entrega

En PowerShell, dentro de la carpeta del proyecto:

```powershell
Copy-Item .env.example .env
notepad .env
python -m unittest discover -s tests -v
python -m scripts.verify_servers
python -m src.chatbot
```

En `.env` se debe colocar la clave real de Anthropic. La clave nunca debe subirse a
GitHub.

## Demostración recomendada

1. Ejecutar las pruebas y mostrar que terminan en `OK`.
2. Ejecutar `python -m scripts.verify_servers` y mostrar los tres resultados `PASS`.
3. Iniciar el chatbot y mostrar la conexión con los tres servidores.
4. Escribir `/servers` y `/tools`.
5. Probar contexto con dos preguntas:
   - “¿Quién fue Alan Turing?”
   - “¿En qué fecha nació?”
6. Probar el servidor propio:
   - “Lista las máquinas que tienen advertencia”.
   - “¿Hay repuesto de resistencia para SELL-01?”
   - “Crea una orden de prioridad alta para revisar la resistencia de SELL-01”.
7. Aceptar la confirmación y mostrar el identificador de la nueva orden.
8. Probar los servidores oficiales:
   - “En el espacio de demostración crea un README.md, revisa Git, agrega el archivo y
     realiza un commit con el mensaje `docs: add demo README`”.
9. Escribir `/logs 30` y señalar los mensajes `initialize`, `tools/list` y `tools/call`.
10. Fuera del chatbot, ejecutar:

   ```powershell
   git -C .\demo_workspace log --oneline --max-count=3
   ```

## Capturas que conviene incluir

- Pruebas automáticas finalizadas en `OK`.
- Inicio con los tres servidores conectados.
- Resultado de `/tools`.
- Las dos preguntas que demuestran el contexto.
- Una consulta al servidor de mantenimiento.
- Confirmación y resultado de la creación de una orden.
- Creación de README y commit mediante Filesystem/Git.
- Resultado de `git log --oneline`.
- Resultado de `/logs 30` con solicitudes y respuestas JSON-RPC.
- Repositorio privado de GitHub con README visible y acceso para docentes.

## Guion corto para explicar el proyecto

“Mi aplicación funciona como anfitrión MCP. El chatbot mantiene una conexión con el
LLM por medio de la API de Anthropic y levanta cada servidor MCP como un subproceso.
El cliente envía mensajes JSON-RPC por la entrada estándar y lee las respuestas por la
salida estándar. Primero realiza la inicialización, después obtiene las herramientas y,
cuando el modelo solicita una, envía `tools/call`. Todas esas interacciones quedan
registradas en un archivo JSONL.

Además de Filesystem y Git, implementé un servidor local para mantenimiento industrial.
Este permite consultar máquinas y repuestos, y crear o cerrar órdenes de trabajo. Las
operaciones de escritura solicitan confirmación para que el usuario conserve el control.
La principal dificultad fue coordinar las respuestas por su identificador JSON-RPC y
mantener el historial de mensajes en el formato que espera la API.”

## Conclusiones y comentario sobre el proyecto

La implementación permitió comprobar que MCP funciona como una capa intermedia entre
el modelo de lenguaje y las herramientas externas. El modelo interpreta la solicitud,
pero la acción real es ejecutada por el servidor mediante herramientas con parámetros
definidos.

También se concluyó que JSON-RPC facilita la comunicación porque cada solicitud puede
relacionarse con su respuesta mediante un identificador. Implementar manualmente la
inicialización, el descubrimiento de herramientas y sus llamadas permitió comprender el
protocolo sin depender de FastMCP o de un SDK de MCP.

Como comentario personal, esta primera fase ayudó a entender que el LLM no ejecuta las
acciones directamente, sino que selecciona una herramienta y utiliza el resultado para
responder. La parte más complicada fue coordinar los mensajes JSON-RPC y mantener limpia
la salida estándar del servidor. En la segunda entrega se podrá conservar la misma lógica,
adaptarla a un servidor remoto y analizar la comunicación con Wireshark.

## Qué no corresponde todavía

La versión remota en la nube, el transporte Streamable HTTP y el análisis con Wireshark
pertenecen a la segunda parte. No es necesario presentarlos como terminados en esta
entrega.

## Lista final antes de subir

- [ ] El catedrático aprobó el caso industrial.
- [ ] La clave está únicamente en `.env`.
- [ ] Las pruebas terminan en `OK`.
- [ ] Los tres servidores aparecen como conectados.
- [ ] El escenario de Filesystem/Git produce un commit real.
- [ ] El log contiene inicialización, descubrimiento y llamadas.
- [ ] El README está en inglés.
- [ ] `docs/Reporte_Entrega_1.pdf` contiene únicamente los incisos 8 y 10.
- [ ] El repositorio de GitHub es privado.
- [ ] Docentes y auxiliares tienen acceso.
- [ ] Los commits reflejan avances reales y graduales.
