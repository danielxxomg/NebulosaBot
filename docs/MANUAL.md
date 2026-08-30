# NebulosaBot — Manual

> Bot de Discord para moderación, tickets, economía y saludos. Diseñado para servidores que quieren gestionar todo desde un solo lugar.

---

## Inicio Rápido

Propósito: punto de entrada para invitar el bot, configurar el servidor y desplegar el panel de tickets en minutos. NebulosaBot expone 8 módulos y 47 comandos exclusivamente slash; los embeds usan paleta violeta/púrpura vía `bot/utils/brand.py` (`brand.ACCENT`). Idioma por defecto `es`.

### Primeros pasos

1. **Invita el bot** al servidor con los permisos necesarios (gestión de canales, expulsar miembros, moderar miembros, gestionar roles).
2. **Ejecuta `/setup`** — comando exclusivamente slash, sin parámetros, solo administradores (`@is_admin()` + `default_permissions administrator`). Abre el panel persistente donde se edita categoría de tickets, rol de moderador, canal de logs e idioma. No toma objetos de Discord como argumentos.
3. **Espera la sincronización automática** — `setup_hook` ejecuta `tree.sync()` al iniciar; no existe comando `/sync` vigente. Los comandos aparecen tras el reinicio sin acción manual.
4. **Despliega el panel de tickets** con `/ticket_panel` en el canal donde quieras que los usuarios abran tickets.
5. **Verifica**

| Comando | Qué revisar |
|---------|-------------|
| `/ping` | Latencia WebSocket en ms |
| `/status` | Base de datos conectada, caché activo, configuración cargada |

Idioma por defecto: **`es`** (español). Si no se configura otro, todas las respuestas usan `es`; `en` solo cuando `language: en` está guardado o el cliente Discord está en inglés para descripciones localizadas. Las descripciones se localizan por cliente; los nombres permanecen en inglés.

---

## Comandos de Usuario

Propósito: comandos disponibles para todos los usuarios sin rol especial, con respuestas permanentes o efímeras según el estándar.

### `/ping` — latencia

- **Descripción**: Muestra la latencia WebSocket del bot.
- **Sintaxis**: `/ping`
- **Permiso**: todos (`everyone`)
- **Parámetros**: — (ninguno)
- **Ejemplo**: `/ping` → embed `Latencia WebSocket: 42 ms` (efímero)

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | — |

### `/help` — ayuda

- **Descripción**: Muestra los comandos agrupados por módulo, paginado.
- **Sintaxis**: `/help` · `/help module:Core`
- **Permiso**: todos
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `module` | `string` | No | Nombre del módulo a detallar |

- **Ejemplo**: `/help` → lista paginada; `/help module:Sentinel` → embed con `/warn`, `/mute`, etc. Solo sintaxis `/comando`.

### `/avatar` — avatar

- **Descripción**: Muestra el avatar del usuario a 1024 px vía `set_image`.
- **Sintaxis**: `/avatar` · `/avatar member:@usuario`
- **Permiso**: todos
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | No | Usuario objetivo (por defecto tú) |

- **Ejemplo**: `/avatar member:@Ana` → embed con `https://cdn.discordapp.com/...?size=1024`

### `/serverinfo` — info del servidor

- **Descripción**: Resumen del servidor (nombre, dueño, miembros, canales, roles, fecha de creación).
- **Sintaxis**: `/serverinfo`
- **Permiso**: todos
- **Parámetros**: —

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | Solo en servidor; en DM error vía `t()` |

- **Ejemplo**: `/serverinfo` → embed con dueño y contadores.

### `/userinfo` — info de usuario

- **Descripción**: Ficha del miembro (ID, roles, fecha de ingreso y creación).
- **Sintaxis**: `/userinfo` · `/userinfo member:@usuario`
- **Permiso**: todos
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | No | Miembro a consultar |

- **Ejemplo**: `/userinfo member:@Luis` → roles listados (máx. 20 + “y N más”).

### `/dice` — dado

- **Descripción**: Tira un dado con número configurable de caras.
- **Sintaxis**: `/dice` · `/dice sides:20`
- **Permiso**: todos (permanente, 1/5 s cooldown, sin escritura a DB)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `sides` | `integer 2-100` | No | Caras del dado (por defecto 6) |

- **Ejemplo**: `/dice sides:20` → `Tiraste un 14 (d20)`. El nombre permanece `dice` en todos los locales; la descripción se localiza vía `Translator` (`es` por defecto).

### `/banana` — banana

- **Descripción**: Imagen aleatoria de banana con medición 2-30 cm.
- **Sintaxis**: `/banana`
- **Permiso**: todos (permanente, sin DB)
- **Parámetros**: —

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | — |

- **Ejemplo**: `/banana` → embed + `attachment://banana_03.webp` con `12 cm`.

### `/8ball` — bola 8

- **Descripción**: Responde a una pregunta con 20 variantes localizadas.
- **Sintaxis**: `/8ball question:¿voy a aprobar?`
- **Permiso**: todos (permanente, sin DB)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `question` | `string` | Sí | Pregunta a la bola 8 |

- **Ejemplo**: `/8ball question:¿hoy es mi día?` → `**Q:** ¿hoy es mi día? **A:** Sí, definitivamente.` Título vía `ocio.8ball.embed_title`.

### `/daily` — recompensa diaria

- **Descripción**: Reclama monedas diarias con racha.
- **Sintaxis**: `/daily`
- **Permiso**: todos (permanente)
- **Parámetros**: —

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | Cooldown 24 h; `stellar.daily.cooldown_description` con `{remaining}` formateado `Xh Ym` |

- **Ejemplo**: `/daily` → `Recibiste 100 monedas. Racha 3 días` o `puedes reclamar de nuevo en 22h 0m` (efímero si en cooldown).

### `/coins` — saldo

- **Descripción**: Consulta saldo de monedas.
- **Sintaxis**: `/coins` · `/coins member:@usuario`
- **Permiso**: todos (permanente)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | No | Usuario a consultar |

- **Ejemplo**: `/coins` → `Tienes 250 monedas` vía `t()`.

### `/leaderboard` — clasificación

- **Descripción**: Top 10 por XP o monedas.
- **Sintaxis**: `/leaderboard lb_type:xp` · `/leaderboard lb_type:coins`
- **Permiso**: todos (permanente)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `lb_type` | `enum xp\|coins` | No | Métrica (por defecto `xp`) |

- **Ejemplo**: `/leaderboard lb_type:coins` → embed top 10 por monedas.

### `/rank` — tarjeta de rango

- **Descripción**: Imagen de nivel, XP y posición.
- **Sintaxis**: `/rank` · `/rank member:@usuario`
- **Permiso**: todos (permanente)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | No | Usuario objetivo |

- **Ejemplo**: `/rank member:@Ana` → imagen con `Nivel 7 — 420/600 XP — #3`.

---

## Comandos de Moderación

Propósito: acciones de moderación invocables exclusivamente vía slash y protegidas por `can_check` y la matriz de permisos.

### `/warn` — advertir

- **Descripción**: Registra una advertencia (`WARN`) y puede escalar a mute/kick según umbrales.
- **Sintaxis**: `/warn member:@usuario reason:spam`
- **Permiso**: `moderation.warn` vía `@can_check("moderation.warn")`; `default_permissions moderate_members`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Miembro a advertir |
| `reason` | `string` | Sí | Motivo |

- **Ejemplo**: `/warn member:@Troll reason:spam` → embed `Miembro advertido` vía `t()`. Sin permiso → `CheckFailure` efímero.

### `/unwarn` — revocar advertencia

- **Descripción**: Elimina la advertencia activa más reciente.
- **Sintaxis**: `/unwarn member:@usuario`
- **Permiso**: `moderation.warn`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Miembro |

- **Ejemplo**: `/unwarn member:@Troll` → `Advertencia revocada`.

### `/mute` — silenciar

- **Descripción**: Aplica timeout (por defecto 1 h) con duración parseada.
- **Sintaxis**: `/mute member:@usuario duration:2h reason:ruido` · `/mute member:@usuario`
- **Permiso**: `moderation.mute`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Miembro |
| `duration` | `string` | No | Duración (`1h`, `30m`, por defecto 1h) |
| `reason` | `string` | No | Motivo |

- **Ejemplo**: `/mute member:@Troll duration:30m` → timeout 30 m.

### `/unmute` — quitar silencio

- **Descripción**: Remueve timeout.
- **Sintaxis**: `/unmute member:@usuario`
- **Permiso**: `moderation.mute`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Miembro |

- **Ejemplo**: `/unmute member:@Troll`.

### `/kick` — expulsar

- **Descripción**: Expulsa con `ConfirmCancelView`; resultado permanente vía `t()`.
- **Sintaxis**: `/kick member:@usuario reason:abuso`
- **Permiso**: `moderation.kick`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Miembro |
| `reason` | `string` | Sí | Motivo |

- **Ejemplo**: `/kick member:@Troll reason:abuso` → diálogo Confirm/Cancel efímero, luego embed permanente.

### `/lock` / `/unlock` — canal

- **Descripción**: Deniega/restaura `send_messages` para `@everyone`.
- **Sintaxis**: `/lock` · `/lock channel:#general` · `/unlock` · `/unlock channel:#general`
- **Permiso**: `moderation` (moderadores, `default_permissions moderate_members`)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `channel` | `Channel` | No | Canal objetivo (por defecto actual) |

- **Ejemplo**: `/lock channel:#anuncios` → `@everyone` sin enviar mensajes.

### `/modlogs` — historial

- **Descripción**: Lista infracciones paginadas (5 por página) con filtros.
- **Sintaxis**: `/modlogs member:@usuario` · `/modlogs member:@usuario type:WARN after:2026-01-01`
- **Permiso**: `moderate_members` (ephemeral)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Usuario |
| `type` | `enum` | No | Tipo (WARN, MUTE, KICK, BAN) |
| `after` | `date ISO` | No | Desde fecha |

- **Ejemplo**: `/modlogs member:@Troll type:MUTE` → paginador `EmbedPaginator`.

### `/tempban` — baneo temporal

- **Descripción**: Banea temporalmente; `expiresAt` se calcula tras Confirm (sin drift).
- **Sintaxis**: `/tempban member:@usuario duration:24h reason:abuso`
- **Permiso**: `moderation.ban` + `ban_members`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Usuario |
| `duration` | `string` | Sí | Duración (`24h`, `7d`) vía `parse_duration_optional` |
| `reason` | `string` | Sí | Motivo |

- **Ejemplo**: `/tempban member:@Troll duration:24h` → `ConfirmCancelView`, luego `BAN expiresAt=ahora+24h` + `member.ban()`.

### `/unban` — desbanear

- **Descripción**: Levanta baneo activo (idempotente) usando `UnbanTarget` tipado.
- **Sintaxis**: `/unban user_id:123456789`
- **Permiso**: `moderation.ban` + `ban_members`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `user_id` | `string` | Sí | ID del usuario |

- **Ejemplo**: `/unban user_id:123` → desbaneo + `guild.unban` o info efímera si no había baneo.

Jerarquía: `_validate_target` deniega si `author.top_role <= target.top_role` salvo dueño del servidor; sumado al check de jerarquía del bot.

---

## Comandos de Administración

Propósito: acciones destructivas o de configuración global, solo administradores o matriz equivalente, exclusivamente slash.

### `/ban` — banear

- **Descripción**: Banea con `delete_days` 0-7 y confirmación.
- **Sintaxis**: `/ban member:@usuario reason:abuso delete_days:1`
- **Permiso**: `moderation.ban` vía `@can_check("moderation.ban")`; `default_permissions ban_members`; administradores pasan implícitamente, matriz `moderation.ban` o fallback `modRoleId`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `member` | `User` | Sí | Usuario |
| `reason` | `string` | Sí | Motivo |
| `delete_days` | `integer 0-7` | No | Días de mensajes a borrar (0 por defecto) |

- **Ejemplo**: `/ban member:@Troll reason:abuso delete_days:1` → `ConfirmCancelView` y luego baneo permanente.

### `/setup` — panel de configuración

- **Descripción**: Abre el panel persistente no efímero de configuración (tickets, bienvenida, despedida, registro, idioma). Cero parámetros.
- **Sintaxis**: `/setup`
- **Permiso**: `administrator` vía `@is_admin()` + `default_permissions administrator`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | Sin parámetros; todo en el panel |

- **Ejemplo**: `/setup` → embed del panel con `SetupPanelView` y breadcrumb `Panel • tickets`. Solo administradores; sin permiso → error efímero vía `t()`.

### `/ticket_panel` — desplegar panel

- **Descripción**: Despliega el mensaje con botón `Abrir Ticket` en el canal actual.
- **Sintaxis**: `/ticket_panel` · `/ticket_panel title:Soporte description_text:Ayuda`
- **Permiso**: `administrator`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `title` | `string` | No | Título del embed |
| `description_text` | `string` | No | Descripción del embed |

- **Ejemplo**: `/ticket_panel title:Soporte` → panel desplegado y `ticketPanelMessageId` persistido.

### `/create_category` — crear categoría

- **Descripción**: Crea categoría de tickets con orden por servidor.
- **Sintaxis**: `/create_category name:Soporte emoji:🎫 description:General position:1`
- **Permiso**: `administrator`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `name` | `string` | Sí | Nombre único por guild |
| `emoji` | `string` | No | Emoji |
| `description` | `string` | No | Descripción |
| `position` | `integer` | No | Orden |

- **Ejemplo**: `/create_category name:Soporte` → `Categoría creada ID abc`.

### `/list_categories` — listar

- **Descripción**: Lista categorías activas ordenadas.
- **Sintaxis**: `/list_categories`
- **Permiso**: `administrator`
- **Parámetros**: —

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | — |

- **Ejemplo**: `/list_categories` → embed `📋 Categorías de Tickets`.

### `/delete_category` — eliminar

- **Descripción**: Elimina categoría sin tickets abiertos; guard `@is_admin()`.
- **Sintaxis**: `/delete_category category_id:uuid`
- **Permiso**: `administrator` (`@is_admin()` + `default_permissions administrator`)
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `category_id` | `string UUID` | Sí | ID de la categoría |

- **Ejemplo**: `/delete_category category_id:abc` → `Categoría eliminada` o `Categoría en uso` si hay tickets abiertos.

### `/configure_fields` — campos personalizados

- **Descripción**: Define `field_definitions` JSON (máx. 3 campos) por categoría.
- **Sintaxis**: `/configure_fields help` · `/configure_fields set category_id:abc fields_json:[{"key":"nick","label":"Apodo"}]`
- **Permiso**: `administrator`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `category_id` | `string` | Sí (para `set`) | ID categoría |
| `fields_json` | `string JSON` | Sí (para `set`) | Array JSON de definiciones |

- **Ejemplo**: `/configure_fields set category_id:abc fields_json:[]` → campos borrados.

### `/welcome` / `/goodbye` — saludos (grupo)

- **Descripción**: Configura canal, estado, mensaje y tarjeta de bienvenida/despedida.
- **Sintaxis**: `/welcome` · `/welcome channel channel:#bienvenida` · `/welcome toggle` · `/welcome message template:Hola {user}` (análogo `goodbye`)
- **Permiso**: `administrator`
- **Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `channel` | `Channel` | No | Canal objetivo |
| `template` | `string` | No | Plantilla con `{user}`, `{server}`, `{mention}` |

- **Ejemplo**: `/welcome channel channel:#bienvenida` → canal configurado.

### `/welcome_test` / `/goodbye_test` — prueba de tarjeta

- **Descripción**: Envía tarjeta de ejemplo (efímero).
- **Sintaxis**: `/welcome_test` · `/goodbye_test`
- **Permiso**: `administrator`
- **Parámetros**: —

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| — | — | — | — |

- **Ejemplo**: `/welcome_test` → imagen de bienvenida de prueba.

---

## Configuración

Propósito: persistencia por servidor, caché y permisos que sostienen todos los comandos slash.

### Servidor (`/setup`)

`/setup` guarda configuración por `guild_id` en la base de datos y en `GuildService`. Todos los campos son editables desde el panel; no hay parámetros en el comando. Ejecutar `/setup` no cambia campos por sí mismo.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ticket_category` | Categoría Discord | Dónde se crean los canales de ticket (obligatorio para tickets) |
| `mod_role` | Rol | Rol moderador (`modRoleId`) |
| `log_channel` | Canal de texto | Canal de logs (`logChannelId`) |
| `language` | `es` / `en` | Idioma del bot; por defecto `es` |

`prefix` persiste como dato (`nb!` por defecto, luego `FALLBACK_PREFIX`) pero es **solo dato**: `get_prefix` resuelve a `[]` siempre y ningún comando es invocable por prefijo. Cambiar `prefix` no habilita dispatch.

### Roles y permisos

Dos capas:

1. **Discord** (`@app_commands.default_permissions`): visibilidad en el picker.
2. **Runtime** (`@can_check`, `@is_mod()`, `@is_admin()`): validación vía `app_commands.check` exclusivamente (prefijo inerte).

| Nivel | Check | Comandos |
|-------|-------|----------|
| Usuario | ninguno | `/ping`, `/help`, `/avatar`, `/serverinfo`, `/userinfo`, `/dice`, `/banana`, `/8ball`, `/daily`, `/coins`, `/leaderboard`, `/rank` |
| Moderador | `@is_mod()` o `@can_check("moderation.*")` | `/status`, `/warn`, `/unwarn`, `/mute`, `/unmute`, `/kick`, `/lock`, `/unlock`, `/modlogs`, `/tempban`, `/unban`, tickets (`/ticket_panel` requiere admin, resto tickets según matriz) |
| Administrador | `@is_admin()` | `/ban`, `/setup`, `/delete_category`, `/welcome`, `/goodbye`, etc. |

Matriz `permissionMatrix` (7 claves): `moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage`. Orden de `can()`: DM→deny, admin→pass, matriz presente→intersección de roles, `moderation.*` sin clave→fallback `modRoleId`, resto sin clave→deny. Claves desconocidas → deny.

### Idioma

- `language: es` — español neutro, por defecto: `es` (default: `es`).
- `language: en` — inglés.
- Descripciones slash se localizan por cliente Discord vía `LocaleTranslator` y `locale_str` (`slash.descriptions.*`), no por servidor. Idioma del cliente (client locale) determina descripciones; los nombres permanecen en inglés. Las descripciones slash son client-localized.

### Caché y base de datos

- **Caché**: `TTLCache` con claves `{guild_id}:config` vía `cache_key(guild_id, entity)` (aislamiento por guild).
- **Lecturas**: `cache → DB → poblar caché`.
- **DB**: Supabase Postgres async (`create_client` con `AsyncClientOptions`); `IF NOT EXISTS` en migraciones para re-ejecución idempotente; sin FK en runtime (validación a nivel app).

---

## Sistema de Tickets

Propósito: ciclo completo de tickets con panel, categorías, campos, sub-tickets, notas e integridad, operado íntegramente por slash.

### Flujo

```
Panel → Clic Abrir → Selector de categoría → Modal (título + descripción + hasta 3 campos custom) → Canal en categoría Discord → Embed fijado + botones → Claim/Transfer/Unclaim/Cierre/Reopen
```

### Panel

`/ticket_panel` en el canal deseado envía embed con botón `ticket:open`. Al hacer clic: selector de categorías si hay varias → modal → canal ` {category}-{username}-{number}` en la categoría configurada → embed de bienvenida fijado.

### Categorías y campos

Cada categoría puede definir hasta 3 campos custom mostrados en el modal (`key`/`label`/`style`/`required`/`max_length`/`placeholder`). Vía `/configure_fields set`. Ejemplo JSON: `[{"key":"player_nick","label":"Apodo","style":"short","required":true}]`. Almacenados en `field_definitions` de la categoría y renderizados en el embed.

### Acciones de staff

| Acción | Comando / Interacción | Descripción |
|--------|------------------------|-------------|
| **Claim** | Botón `Reclamar` | Toma propiedad del ticket |
| **Transferir** | `/transfer member:@staff` | Cambia responsable |
| **Unclaim** | `/unclaim` | Libera a `open`/`claimedBy:null` (solo claimer o moderador vía `TicketService.check_can_unclaim`, sin clave de matriz nueva) |
| **Cerrar** | Botón `Cerrar` | Diálogo Confirm/Cancel efímero |
| **Reabrir** | `/reopen` o `/reopen ticket_ref:#0003` | Restaura ticket cerrado |
| **Nota** | `/note add content:texto` · `/note list` · `/note delete note_id:uuid` | Notas privadas de staff |
| **Sub-ticket** | `/subticket create parent_id:uuid` | Ticket secundario vinculado al padre |
| **Integridad** | `/sweep_integrity` · `/repair_ticket ticket_ref:#0003` | Cierra zombies con corroboración de Discord |

### Cierre — confirmación y temporizador `close-confirmation`

Al hacer clic en **Cerrar**, el bot muestra diálogo efímero Confirm/Cancel (30 s):

- **Confirmar**: genera transcript, marca ticket cerrado en DB, envía mensaje único con `5` y lo edita `5→4→3→2→1` (1 s entre ediciones), espera 1 s y elimina el canal.
- **Cancelar** o **cerrar el diálogo**: sin cambios.
- **Ignorar** (expira): equivale a cancelar.

El cierre automático (48 h sin actividad, revisión cada hora) elimina sin cuenta regresiva.

**Temporizador con coma (`,`)**: no es un prefijo de comando. La única conducta con `,` vive en `TicketsCog.on_message` y está especificada por `close-confirmation`, fuera del framework de comandos (slash-only). Escribir `,` en un canal de ticket dispara el temporizador de confirmación de cierre según `close-confirmation`, no una invocación de comando. Ningún `get_prefix` lo habilita.

### Claim sobre ticket ya reclamado

Si un moderador hace clic en **Claim** con responsable existente, se muestra diálogo efímero con claimer actual; al confirmar se transfiere.

### Nombres de canal

Formato `{category}-{username}-{number}`: `soporte-danielxx-0042`. Sanitiza tildes, espacios→guiones, no alfanuméricos eliminados; trunca a 100 preservando `-{número}`. Fallback `ticket`/`user` si no resoluble.

### Sub-tickets e integridad

Sub-tickets heredan categoría Discord del padre y referencia al padre. `sweep_integrity` y `repair_ticket` verifican existencia en Discord antes de mutar.

---

## Comandos Slash

Propósito: inventario canónico de todos los comandos disponibles exclusivamente vía slash y su comportamiento unificado.

Todos los comandos se invocan exclusivamente como slash (`/comando`) — **no existe ruta por prefijo**; `get_prefix` resuelve a `[]` y `bot-core` es slash-only. No quedan comandos slash híbridos registrados (AST verifica 0 en `bot/cogs`). Errores de permisos o validación se muestran como respuestas **efímeras** (solo visibles para el invocador) localizadas vía `t()`; los comandos de ocio/economía listados como permanentes responden sin `ephemeral`. Los nombres de comandos permanecen en inglés; las descripciones se localizan por cliente Discord (`es` por defecto). El temporizador `,` no es un comando y vive únicamente en `TicketsCog.on_message` bajo `close-confirmation`, fuera del framework.

### Lista completa (sintaxis slash únicamente, sin prefijo)

| Comando | Sintaxis slash | Permiso | Respuesta |
|---------|----------------|---------|-----------|
| `/ping` | `/ping` | todos | efímera |
| `/help` | `/help [module]` | todos | efímera |
| `/status` | `/status` | moderador | efímera |
| `/avatar` | `/avatar [member]` | todos | permanente |
| `/serverinfo` | `/serverinfo` | todos | permanente |
| `/userinfo` | `/userinfo [member]` | todos | permanente |
| `/dice` | `/dice [sides:2-100]` | todos | permanente |
| `/banana` | `/banana` | todos | permanente |
| `/8ball` | `/8ball question` | todos | permanente |
| `/daily` | `/daily` | todos | efímera si en cooldown, permanente si éxito |
| `/coins` | `/coins [member]` | todos | permanente |
| `/leaderboard` | `/leaderboard [lb_type]` | todos | permanente |
| `/rank` | `/rank [member]` | todos | permanente (imagen) |
| `/warn` | `/warn member reason` | `moderation.warn` | efímera/permanente vía `t()` |
| `/unwarn` | `/unwarn member` | `moderation.warn` | efímera |
| `/mute` | `/mute member [duration] [reason]` | `moderation.mute` | efímera/permanente |
| `/unmute` | `/unmute member` | `moderation.mute` | efímera |
| `/kick` | `/kick member reason` | `moderation.kick` | `ConfirmCancelView` + permanente |
| `/ban` | `/ban member reason [delete_days]` | `moderation.ban` | `ConfirmCancelView` + permanente |
| `/tempban` | `/tempban member duration reason` | `moderation.ban` | `ConfirmCancelView` + permanente |
| `/unban` | `/unban user_id` | `moderation.ban` | efímera/permanente |
| `/lock` | `/lock [channel]` | moderador | efímera/permanente |
| `/unlock` | `/unlock [channel]` | moderador | efímera/permanente |
| `/modlogs` | `/modlogs member [type] [after]` | `moderate_members` | efímera paginada |
| `/ticket_panel` | `/ticket_panel [title] [description_text]` | administrador | efímera |
| `/create_category` | `/create_category name [emoji]` | administrador | efímera |
| `/list_categories` | `/list_categories` | administrador | efímera |
| `/delete_category` | `/delete_category category_id` | administrador (`@is_admin`) | efímera |
| `/configure_fields` | `/configure_fields help` · `/configure_fields set category_id fields_json` | administrador | efímera |
| `/subticket` | `/subticket create [parent_id]` | `tickets.manage` | efímera |
| `/reopen` | `/reopen [ticket_ref]` | `tickets.manage` | efímera |
| `/transfer` | `/transfer member` | `tickets.manage` | efímera |
| `/unclaim` | `/unclaim` | claimer o moderador (servicio) | efímera vía `t()` |
| `/note` | `/note add content` · `/note list` · `/note delete note_id` | `tickets.manage` | efímera |
| `/sweep_integrity` | `/sweep_integrity` | `tickets.manage` | efímera |
| `/repair_ticket` | `/repair_ticket ticket_ref` | moderador/administrador | efímera |
| `/setup` | `/setup` | administrador | no efímera (panel) |
| `/welcome` | `/welcome` · `/welcome channel` · `/welcome toggle` · `/welcome message` | administrador | efímera/permanente según subcomando |
| `/goodbye` | `/goodbye` · `/goodbye channel` · `/goodbye toggle` · `/goodbye message` | administrador | efímera |
| `/welcome_test` | `/welcome_test` | administrador | efímera (prueba) |
| `/goodbye_test` | `/goodbye_test` | administrador | efímera (prueba) |

Los errores se responden como embeds efímeros localizados (`common.error.check_failure_*`, `missing_permissions_*` vía `t()`), nunca como prefijo. La sincronización del árbol es automática (`tree.sync` en `setup_hook`); no hay `/sync` manual.

---

---

*Última actualización: agosto 2026. Basado en el código fuente de NebulosaBot (slash-only). Paleta violeta y brand.ACCENT según brand tokens.*
