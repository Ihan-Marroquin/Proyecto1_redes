# Proyecto 1 de Redes

Este es el avance de la primera entrega del proyecto. Hice un chatbot que se
usa desde la consola y que puede comunicarse con varios servidores MCP.

Por ahora el proyecto trabaja solamente con servidores locales. Uno de ellos lo
hice para llevar información de mantenimiento de máquinas. Los otros dos sirven
para hacer pruebas con archivos y con Git.

## Qué hace

- Permite conversar con Claude desde la terminal.
- Mantiene el contexto de la conversación mientras el programa está abierto.
- Consulta máquinas, repuestos y órdenes de mantenimiento.
- Pide confirmación antes de guardar o modificar datos.
- Guarda un registro de la comunicación con los servidores.
- Incluye pruebas para revisar que las funciones principales trabajen bien.

La comunicación con MCP se hizo directamente con mensajes JSON-RPC, sin usar un
SDK que hiciera esa parte automáticamente.

## Antes de ejecutarlo

Se necesita tener instalado lo siguiente:

- Python 3.11 o una versión más reciente.
- Git.
- Node.js 22 o superior.
- `npx`, `uv` y `uvx`.
- Una clave de la API de Anthropic.

Se puede revisar desde PowerShell con estos comandos:

```powershell
python --version
git --version
node --version
npx --version
uvx --version
```

Si hace falta `uvx`, se puede instalar así:

```powershell
python -m pip install uv
```

## Configuración

Hay que crear una copia del archivo de ejemplo:

```powershell
Copy-Item .env.example .env
notepad .env
```

Después se coloca la clave de Anthropic dentro de `.env`:

```env
ANTHROPIC_API_KEY=colocar_la_clave_aqui
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

El archivo `.env` no se debe subir a GitHub porque contiene la clave personal.
Por eso ya está agregado al `.gitignore`.

## Cómo correrlo

Desde la carpeta del proyecto:

```powershell
python -m src.chatbot
```

También se puede iniciar con:

```powershell
.\run.ps1
```

La primera vez puede tardar un poco mientras se descargan los servidores que
usan `npx` y `uvx`.

Estos son algunos comandos que se pueden escribir dentro del chatbot:

- `/servers`: muestra los servidores conectados.
- `/tools`: muestra las herramientas disponibles.
- `/logs 20`: enseña los últimos 20 registros.
- `/clear`: limpia la conversación.
- `/exit`: cierra el programa.

## Pruebas

Para correr las pruebas del proyecto:

```powershell
python -m unittest discover -s tests -v
```

Estas pruebas no utilizan la API de Anthropic, por lo que no consumen créditos.

También se puede revisar si los servidores responden correctamente:

```powershell
python -m scripts.verify_servers
```

Al terminar deberían aparecer los servidores `maintenance`, `filesystem` y
`git`.

## Ejemplos

Algunas consultas para probar el servidor de mantenimiento son:

```text
¿Qué máquinas tienen una advertencia?
¿Hay repuesto de resistencia para la máquina SELL-01?
Crea una orden de prioridad alta para revisar la resistencia de SELL-01.
```

La última consulta pide confirmación porque crea una nueva orden.

También se puede probar el contexto de la conversación:

```text
¿Quién fue Alan Turing?
¿En qué fecha nació?
```

## Primera entrega

En esta parte se trabajó con la conexión local. El servidor remoto y el análisis
en Wireshark se harán en la segunda entrega.

El reporte se encuentra en
[`docs/Reporte_Entrega_1.pdf`](docs/Reporte_Entrega_1.pdf).

El archivo [`ENTREGA_1.md`](ENTREGA_1.md) contiene la explicación más detallada
de las pruebas y de los mensajes usados para comunicarse con MCP.
