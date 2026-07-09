# NebulosaBot — Manual

> Bot de Discord para moderación, tickets, economía y saludos. Diseñado para servidores que quieren gestionar todo desde un solo lugar.

---

## 1. Vista general

NebulosaBot es un bot de Discord con **8 módulos** y **47 comandos** (slash + prefijo). Cubre moderación, sistema de tickets con campos personalizados, economía con niveles, tarjetas de bien/despedida, y utilidades varias.

| Módulo | Propósito | Audiencia |
|--------|-----------|-----------|
| Core | Infraestructura: latencia, estado, ayuda, sincronización | Todos / Admin |
| Sentinel | Moderación: advertencias, mute, kick, ban, bloqueo de canales | Mod / Admin |
| Tickets | Sistema de tickets con paneles, categorías, notas y sub-tickets | Mod / Admin |
| Stellar | Economía: monedas diarias, ranking, tabla de líderes | Todos |
| Greetings | Tarjetas de bienvenida y despedida configurables | Admin |
| Utility | Información de usuarios y servidores | Todos |
| Ocio | Comandos casuales: dados, banana | Todos |
| Setup | Configuración del servidor (categoría de tickets, rol de mod, canal de logs, idioma) | Admin |

**Formato de comandos**: todos son híbridos — funcionan como slash (`/comando`) y como prefijo (configurable por servidor). El bot soporta español e inglés para las respuestas en tiempo real; los nombres de comandos y sus descripciones en Discord permanecen en inglés.

**Ayuda en vivo**: usa `/help` para listar todos los módulos disponibles, o `/help <módulo>` para ver los comandos de un módulo específico. Este manual es una guía de referencia; `/help` es siempre la fuente de verdad sobre comandos registrados.

---

## 2. Inicio rápido

### Primeros pasos

1. **Invita el bot** al servidor con los permisos necesarios (gestión de canales, expulsar/miembros, moderar miembros).
2. **Ejecuta `/setup`** para configurar el servidor:

   | Parámetro | Requerido | Descripción |
   |-----------|-----------|-------------|
   | `ticket_category` | Sí | Categoría de Discord donde se crearán los canales de ticket |
   | `mod_role` | No | Rol de moderador (para comandos de moderación) |
   | `log_channel` | No | Canal donde se registran las acciones de moderación |
   | `language` | No | Idioma del bot: `es` o `en` (por defecto: `en`) |

3. **Sincroniza comandos** con `/sync` (solo admin) para que Discord registre los comandos slash actualizados.
4. **Despliega el panel de tickets** con `/ticket_panel` en el canal donde quieras que los usuarios abran tickets.

### Verificar que todo funciona

| Comando | Qué revisar |
|---------|-------------|
| `/ping` | Latencia WebSocket en ms |
| `/status` | Base de datos conectada, caché activo, configuración cargada |

---

## 3. Configuración

### Configuración del servidor (`/setup`)

El comando `/setup` guarda la configuración por servidor en la base de datos. Solo administradores pueden ejecutarlo.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ticket_category` | Categoría de Discord | **Obligatorio**. Donde se crean los canales de ticket |
| `mod_role` | Rol | Rol que tiene permisos de moderación (warn, mute, kick, lock) |
| `log_channel` | Canal de texto | Canal para el registro de acciones de moderación |
| `language` | `es` / `en` | Idioma de las respuestas del bot |

Ejecutar `/setup` de nuevo sobrescribe los campos proporcionados; los campos omitidos conservan su valor anterior.

### Roles y permisos

El bot usa **dos capas de permisos**:

1. **Permisos de Discord** (`@app_commands.default_permissions`): controlan quién ve el comando en el menú de slash commands.
2. **Checks en runtime** (`@is_mod()`, `@is_admin()`): validación adicional al ejecutar el comando.

| Nivel | Check | Comandos |
|-------|-------|----------|
| Usuario | Ninguno | `/ping`, `/help`, `/avatar`, `/serverinfo`, `/userinfo`, `/dados`, `/banana`, `/daily`, `/coins`, `/leaderboard`, `/rank` |
| Moderador | `@is_mod()` | `/status`, `/warn`, `/unwarn`, `/mute`, `/unmute`, `/kick`, `/lock`, `/unlock`, `/modlogs`, todos los comandos de tickets |
| Administrador | `@is_admin()` | `/sync`, `/ban`, `/setup`, `/ticket_panel`, `/create_category`, `/list_categories`, `/delete_category`, `/configure_fields`, `/welcome`, `/goodbye`, `/welcome_test`, `/goodbye_test` |

### Idioma

- `language: es` — respuestas en español neutro.
- `language: en` — respuestas en inglés (por defecto si no se configura).
- Los nombres de comandos y descripciones slash siempre están en inglés (diseño deliberado de Discord).

---

## 4. Estado del bot

### Cómo verificar la salud del bot

| Comando | Qué muestra |
|---------|-------------|
| `/ping` | Latencia del gateway WebSocket en milisegundos |
| `/status` | Estado de la base de datos, caché en memoria, configuración del servidor y latencia |

### Indicadores de `/status`

| Campo | Saludable | Problema |
|-------|-----------|----------|
| Base de datos | ✅ Conectado | ❌ Inalcanzable — revisar conexión a Supabase |
| Caché | ✅ N claves en memoria | ❌ No inicializado — reiniciar el bot |
| Configuración del servidor | ✅ Cargado (muestra prefijo e idioma) | ⚠️ No cargado — ejecutar `/setup` |
| Latencia | < 200 ms | > 500 ms — posible problema de red |

### Arquitectura de caché

El bot usa un modelo **caché → base de datos** para lecturas:

1. Busca en caché RAM primero.
2. Si no encuentra, consulta la base de datos (Supabase).
3. Popula la caché para la próxima lectura.

Las claves de caché incluyen `guild_id` para aislar datos entre servidores.

### Base de datos

- **Proveedor**: Supabase (PostgreSQL).
- **Operaciones**: async, sin bloqueo del event loop.
- **Sin FK en runtime**: Supabase Transaction Mode no aplica foreign keys; la validación de integridad es a nivel de aplicación.

---

## 5. Casos de uso — Usuarios

### Ver tu avatar o el de otro

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Ver tu propio avatar | `/avatar` | Embed con tu avatar a 1024px |
| Ver avatar de otro | `/avatar @usuario` | Embed con el avatar del usuario mencionado |

### Información del servidor y usuarios

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Info del servidor | `/serverinfo` | Embed con dueño, miembros, canales, roles, boosts, fecha de creación |
| Info de un usuario | `/userinfo @usuario` | Embed con ID, roles, fecha de ingreso y creación |

### Economía

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Reclamar monedas diarias | `/daily` | Recompensa de monedas con seguimiento de racha |
| Ver tu balance | `/coins` | Tus monedas actuales |
| Ver balance de otro | `/coins @usuario` | Monedas del usuario mencionado |
| Tabla de líderes XP | `/leaderboard` o `/leaderboard xp` | Top 10 por experiencia |
| Tabla de líderes monedas | `/leaderboard coins` | Top 10 por monedas |
| Ver tu tarjeta de rango | `/rank` | Imagen con tu nivel, XP y posición |
| Ver rango de otro | `/rank @usuario` | Tarjeta de rango del usuario mencionado |

### Diversión

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Tirar un dado de 6 caras | `/dados` | Resultado aleatorio 1-6 |
| Tirar un dado personalizado | `/dados 20` | Resultado aleatorio 1-20 (2-100 caras) |
| Medir en bananas | `/banana` | Imagen de banana con medición aleatoria (2-30 cm) |

---

## 6. Casos de uso — Moderación y administración

### Moderación básica

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Advertir a un miembro | `/warn @usuario razón` | Registra advertencia; posible escalada automática |
| Quitar advertencia | `/unwarn @usuario` | Desactiva la advertencia más reciente |
| Silenciar (timeout) | `/mute @usuario 2h razón` | Timeout por la duración indicada (por defecto: 1h) |
| Quitar silencio | `/unmute @usuario` | Remueve el timeout |
| Expulsar | `/kick @usuario razón` | Expulsa al miembro (con confirmación) |
| Banear | `/ban @usuario razón` | Banea al miembro (solo admin, con confirmación) |
| Bloquear canal | `/lock` o `/lock #canal` | Deniega `send_messages` para @everyone |
| Desbloquear canal | `/unlock` o `/unlock #canal` | Restaura `send_messages` para @everyone |
| Ver historial | `/modlogs @usuario` | Historial de infracciones paginado |
| Filtrar historial | `/modlogs @usuario WARN 2026-01-01` | Filtra por tipo y/o fecha |

### Escalada automática

Al advertir a un miembro, el bot puede escalar automáticamente:

- **N advertencias → mute**: silencia al miembro automáticamente.
- **N advertencias → kick**: expulsa al miembro automáticamente.

Los umbrales de escalada se configuran en la base de datos.

### Sistema de tickets

#### Despliegue del panel

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Crear panel de tickets | `/ticket_panel` | Mensaje con botón "Abrir ticket" en el canal actual |
| Panel con título personalizado | `/ticket_panel title:"Soporte Técnico"` | Panel con título y descripción custom |

#### Categorías de tickets

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Crear categoría | `/create_category "Soporte" emoji:🎫` | Nueva categoría para organizar tickets |
| Listar categorías | `/list_categories` | Lista de todas las categorías activas con IDs |
| Eliminar categoría | `/delete_category <uuid>` | Elimina la categoría (solo si no tiene tickets abiertos) |

#### Campos personalizados por categoría

Cada categoría de ticket puede tener campos de entrada personalizados que el usuario completa al abrir el ticket (vía modal).

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Ver ayuda | `/configure_fields help` | Información sobre el sistema de campos |
| Definir campos | `/configure_fields set <cat_id> '[{"key":"nick","label":"Nickname"}]'` | Campos personalizados para la categoría |
| Limpiar campos | `/configure_fields set <cat_id> '[]'` | Elimina todos los campos de la categoría |

**Formato JSON de campos**: array de objetos con `key` (identificador interno) y `label` (texto visible en el modal). Máximo **3 campos personalizados** por categoría (el modal de Discord permite 5 inputs en total: título + descripción + hasta 3 extras).

#### Sub-tickets

Los sub-tickets permiten derivar un ticket secundario vinculado a uno principal.

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Crear sub-ticket (canal actual) | `/subticket create` | Nuevo ticket vinculado al ticket del canal actual |
| Crear sub-ticket (por ID) | `/subticket create <parent_uuid>` | Nuevo ticket vinculado al ticket especificado |

#### Reabrir, transferir y notas

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Reabrir ticket (canal actual) | `/reopen` | Reabre el ticket cerrado de este canal |
| Reabrir ticket (por referencia) | `/reopen #0003` | Reabre por número, UUID o referencia |
| Transferir ticket | `/transfer @staff` | Transfiere la propiedad del ticket a otro staff |
| Agregar nota | `/note add "texto de la nota"` | Nota privada visible solo para mods |
| Listar notas | `/note list` | Lista todas las notas del ticket (por DM o ephemeral) |
| Eliminar nota | `/note delete <uuid>` | Elimina una nota específica |

#### Cierre automático

Los tickets sin actividad por **48 horas** se cierran automáticamente. El bot revisa cada hora.

### Bienvenida y despedida

#### Configuración

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Ver config de bienvenida | `/welcome` | Muestra canal, estado y mensaje actual |
| Definir canal de bienvenida | `/welcome channel #canal` | Canal donde se envían las tarjetas |
| Activar/desactivar | `/welcome toggle` | Alterna el estado de bienvenida |
| Definir mensaje | `/welcome message "¡Hola {user}!"` | Template con placeholders: `{user}`, `{server}`, `{mention}` |
| Ver config de despedida | `/goodbye` | Muestra canal, estado y mensaje actual |
| Definir canal de despedida | `/goodbye channel #canal` | Canal donde se envían las tarjetas |
| Activar/desactivar despedida | `/goodbye toggle` | Alterna el estado de despedida |
| Definir mensaje de despedida | `/goodbye message "Chau {user}"` | Template con los mismos placeholders |

#### Prueba

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Probar tarjeta de bienvenida | `/welcome_test` | Genera y envía una tarjeta de ejemplo (ephemeral) |
| Probar tarjeta de despedida | `/goodbye_test` | Genera y envía una tarjeta de ejemplo (ephemeral) |

### Administración

| Tarea | Comando | Resultado |
|-------|---------|-----------|
| Sincronizar comandos slash | `/sync` | Registra/actualiza los comandos en Discord |
| Configurar servidor | `/setup` | Ver sección [3. Configuración](#3-configuración) |

---

## 7. Referencia de comandos

### Para todos los usuarios

| Comando | Parámetros | Resultado |
|---------|------------|-----------|
| `/ping` | — | Latencia WebSocket en ms |
| `/help` | `[módulo]` | Lista de módulos o comandos de un módulo |
| `/avatar` | `[@usuario]` | Avatar del usuario a 1024px |
| `/serverinfo` | — | Información del servidor |
| `/userinfo` | `[@usuario]` | Información del usuario |
| `/daily` | — | Reclamar recompensa diaria de monedas |
| `/coins` | `[@usuario]` | Balance de monedas |
| `/leaderboard` | `[xp\|coins]` | Top 10 por XP o monedas |
| `/rank` | `[@usuario]` | Tarjeta de rango como imagen |
| `/dados` | `[caras]` | Tira un dado (2-100 caras, por defecto 6) |
| `/banana` | — | Medición aleatoria en bananas |

### Moderación

| Comando | Parámetros | Permiso | Resultado |
|---------|------------|---------|-----------|
| `/status` | — | Mod | Estado de DB, caché y configuración |
| `/warn` | `<@usuario> <razón>` | Mod | Registra advertencia |
| `/unwarn` | `<@usuario>` | Mod | Quita la advertencia más reciente |
| `/mute` | `<@usuario> [duración] [razón]` | Mod | Timeout (por defecto 1h) |
| `/unmute` | `<@usuario>` | Mod | Remueve timeout |
| `/kick` | `<@usuario> <razón>` | Mod | Expulsa con confirmación |
| `/lock` | `[#canal]` | Mod | Bloquea canal para @everyone |
| `/unlock` | `[#canal]` | Mod | Desbloquea canal |
| `/modlogs` | `<@usuario> [tipo] [después]` | Mod | Historial de infracciones |

### Administración

| Comando | Parámetros | Permiso | Resultado |
|---------|------------|---------|-----------|
| `/ban` | `<@usuario> <razón> [días_borrar]` | Admin | Banea con confirmación (0-7 días de mensajes) |
| `/sync` | — | Admin | Sincroniza árbol de comandos |
| `/setup` | `<categoría_tickets> [rol_mod] [canal_logs] [idioma]` | Admin | Configura el servidor |

### Tickets

| Comando | Parámetros | Permiso | Resultado |
|---------|------------|---------|-----------|
| `/ticket_panel` | `[título] [descripción]` | Mod | Despliega panel con botón de apertura |
| `/create_category` | `<nombre> [emoji] [descripción] [posición]` | Mod | Crea categoría de tickets |
| `/list_categories` | — | Mod | Lista categorías activas |
| `/delete_category` | `<uuid>` | Mod | Elimina categoría (sin tickets abiertos) |
| `/configure_fields help` | — | Mod | Ayuda del sistema de campos |
| `/configure_fields set` | `<uuid_cat> <json_campos>` | Mod | Define campos personalizados |
| `/subticket create` | `[uuid_padre]` | Mod | Crea sub-ticket vinculado |
| `/reopen` | `[referencia]` | Mod | Reabre ticket cerrado |
| `/transfer` | `<@staff>` | Mod | Transfiere ticket |
| `/note add` | `<contenido>` | Mod | Agrega nota privada |
| `/note list` | — | Mod | Lista notas del ticket |
| `/note delete` | `<uuid_nota>` | Mod | Elimina nota |

### Bienvenida y despedida

| Comando | Parámetros | Permiso | Resultado |
|---------|------------|---------|-----------|
| `/welcome` | — | Admin | Muestra config actual |
| `/welcome channel` | `<#canal>` | Admin | Define canal de bienvenida |
| `/welcome toggle` | — | Admin | Activa/desactiva |
| `/welcome message` | `<template>` | Admin | Define mensaje (placeholders: `{user}`, `{server}`, `{mention}`) |
| `/goodbye` | — | Admin | Muestra config actual |
| `/goodbye channel` | `<#canal>` | Admin | Define canal de despedida |
| `/goodbye toggle` | — | Admin | Activa/desactiva |
| `/goodbye message` | `<template>` | Admin | Define mensaje |
| `/welcome_test` | — | Admin | Prueba tarjeta de bienvenida |
| `/goodbye_test` | — | Admin | Prueba tarjeta de despedida |

---

## 8. Tickets en detalle

### Flujo de vida de un ticket

```
Panel → Usuario clickea → Modal (título + campos custom) → Canal creado → Conversación → Cierre
                                                    ↑                                       │
                                                    └── Reopen ←────────────────────────────┘
```

### Panel de tickets

El administrador ejecuta `/ticket_panel` en el canal deseado. El bot envía un embed con un botón. Al hacer clic:

1. Se abre un **menú de categorías** (si hay varias).
2. Al elegir categoría se abre un **modal** con título (obligatorio), descripción (opcional) y hasta 3 campos personalizados de esa categoría.
3. Se crea un canal de texto en la categoría de Discord configurada con `/setup`.
4. El canal recibe un embed de bienvenida (fijado) con los datos del ticket y botones de acción.

### Campos personalizados

Cada categoría puede definir campos que aparecen en el modal de apertura:

```json
[
  {"key": "player_nick", "label": "Nickname del jugador"},
  {"key": "server", "label": "Servidor"},
  {"key": "issue_type", "label": "Tipo de problema"}
]
```

- `key`: identificador interno, sin espacios.
- `label`: texto que ve el usuario en el modal.
- Se almacenan en la base de datos como parte de la categoría.
- Se muestran en el embed del ticket una vez creado.

### Acciones de staff

| Acción | Comando | Descripción |
|--------|---------|-------------|
| **Claim** | Interacción con botón | El staff toma propiedad del ticket |
| **Transferir** | `/transfer @otro_staff` | Cambia el responsable del ticket |
| **Cerrar** | Interacción con botón | Cierra el ticket (archiva el canal) |
| **Reabrir** | `/reopen` o `/reopen #0003` | Restaura un ticket cerrado |
| **Nota** | `/note add "texto"` | Nota privada solo visible para mods |
| **Sub-ticket** | `/subticket create` | Deriva un ticket secundario vinculado |

### Sub-tickets

Útiles cuando un problema requiere seguimiento separado pero vinculado al ticket original:

- Se crean en la misma categoría de Discord que el padre.
- Heredan la configuración de campos personalizados del padre.
- El canal recibe el embed del ticket con referencia al padre.

### Cierre automático

- **Umbral**: 48 horas sin actividad.
- **Frecuencia de revisión**: cada 1 hora.
- **Efecto**: el ticket se marca como cerrado y el canal se archiva.
- La actividad se actualiza con cada mensaje en el canal del ticket.

---

## 9. Deuda conocida y limitaciones

| Tema | Descripción |
|------|-------------|
| **Manual potencialmente desactualizado** | Este manual refleja el código al momento de su creación. Los comandos registrados pueden cambiar con actualizaciones. Usar `/help` como fuente de verdad. |
| **Sin localización de descripciones slash** | Las descripciones de comandos en Discord están en inglés por diseño. Solo las respuestas del bot se localizan (es/en). |
| **Sin README ni PRODUCT.md** | El repositorio no tiene documentación de alto nivel para desarrolladores fuera de `AGENTS.md` (reglas de code review). |
| **Supabase sin FK en runtime** | Transaction Mode de Supabase no aplica foreign keys. La integridad referencial se valida en la aplicación. |
| **Escalada automática con umbrales fijos** | Los umbrales de escalada (warn → mute → kick) requieren configuración en base de datos; no hay comando de Discord para ajustarlos. |
| **Configuración de greetings solo por comandos** | No hay panel visual para configurar bienvenida/despedida; todo se hace por comandos slash. |
| **Imágenes generadas en hilo** | Las tarjetas de rango y bienvenida se generan en un hilo separado (`asyncio.to_thread`) para no bloquear el event loop, pero el rendimiento depende del servidor. |

---

*Última actualización: julio 2026. Basado en el código fuente de NebulosaBot.*
