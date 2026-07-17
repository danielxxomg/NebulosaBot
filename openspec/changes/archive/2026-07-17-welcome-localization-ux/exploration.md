# Exploration: welcome-localization-ux

## Current State

### Guild Language Configuration (Verified via Supabase)

Two guilds exist in production (`public.guild`), both configured with `language: "es"`:

| Guild ID | Prefix | Language | Welcome Enabled | Active |
|---|---|---|---|---|
| `1370640363835887667` | `nb!` | `es` | `false` | `true` |
| `1518709129403695154` | `nb!` | `es` | `false` | `true` |

One guild has active greeting configuration (`public.greeting_config`):

| Guild ID | Welcome | Goodbye | Channel | Card Enabled | Custom Template |
|---|---|---|---|---|---|
| `1518709129403695154` | `true` | `true` | `1518737123132571678` | `true` (both) | `null` (both) |

The guild language is Spanish (`"es"`), welcome and goodbye are both enabled, cards are enabled, and no custom message templates are set.

### i18n System (`bot/core/i18n.py`)

The i18n system works correctly for command responses and embeds:

- `load_locales()` loads `bot/locales/es.json` and `bot/locales/en.json` at startup.
- `GuildService.get_config()` calls `set_guild_language(guild_id, config.language)` on every cache read (hit or miss), populating the module-level `_guild_languages` map.
- `t(guild_id, key, **kwargs)` resolves the guild language, walks dot-notation keys through the locale dict, falls back to `es`, then returns the raw key.
- `LocaleTranslator` handles Discord client-locale mapping for slash command metadata.

**Locale files contain greeting keys for command responses** (config embeds, permission errors, toggle descriptions) but **zero keys for card image text** ("Welcome", "Goodbye", "Member #").

### Welcome Card Generation (`bot/services/image_service.py`)

`generate_greeting_card()` renders a Pillow image with:
- Gradient background (Discord dark theme)
- Circular avatar (128x128)
- **Hardcoded English greeting title** (line 303): `greeting = "Welcome" if card_type == "welcome" else "Goodbye"`
- **Hardcoded English member count** (line 319): `count_text = f"Member #{member_count:,}"`
- No guild icon, no branding, no decorative elements
- Single font (Inter Regular) at two sizes (32pt title, 22pt count)
- Only asset: `assets/fonts/Inter-Regular.ttf`

### Dispatch Flow (`bot/services/greeting_service.py`)

`dispatch_welcome(member)`:
1. Resolves `GreetingConfig` via cache-first `get_config(guild_id)`
2. Checks `welcome_enabled` and `welcome_channel_id` guards
3. If card enabled: calls `generate_greeting_card(username, avatar_url, guild_name, member_count, card_type="welcome")`
4. Formats optional message template with `_format_template(template, member)` supporting `{mention}`, `{user}`, `{server}`
5. Sends card as `discord.File` with optional text content

**The guild language is never queried or passed.** Neither `dispatch_welcome` nor `dispatch_goodbye` reads from `_guild_languages` or passes language/locale to `ImageService`. The card text is always English regardless of guild config.

## Root Cause

**`ImageService.generate_greeting_card()` has two hardcoded English strings that bypass the i18n system entirely:**

```python
# Line 303
greeting = "Welcome" if card_type == "welcome" else "Goodbye"
# Line 319
count_text = f"Member #{member_count:,}"
```

No locale keys exist in `es.json` or `en.json` for these card texts. The `GreetingService` dispatch methods do not resolve or pass the guild language. The i18n pipeline (`set_guild_language` → `t()`) is correctly wired for command responses but was never extended to the image generation path.

## Affected Areas

- `bot/services/image_service.py` — `generate_greeting_card()` lines 303, 319: hardcoded English text
- `bot/services/greeting_service.py` — `dispatch_welcome()` and `dispatch_goodbye()`: do not resolve or pass guild language
- `bot/locales/es.json` — missing card text keys (greeting title, member count)
- `bot/locales/en.json` — missing card text keys
- `bot/cogs/greetings.py` — `welcome_test` and `goodbye_test` commands also call `generate_greeting_card()` without language
- `tests/test_image_service.py` — `TestGenerateGreetingCard`: no language-aware assertions
- `tests/test_greeting_service.py` — `TestDispatchWelcome`/`TestDispatchGoodbye`: no language verification

## Approaches

### Approach A: Add `language` parameter to `generate_greeting_card()`

Add `language: str = "es"` to the method signature. Look up localized greeting title and member count text inside the method by importing `t()` or receiving a locale dict.

- **Pros**: Simple change, backwards compatible (defaults to `"es"`)
- **Cons**: Couples `ImageService` to the `i18n` module; ImageService should remain a pure Pillow renderer
- **Effort**: Low

### Approach B: Pass pre-translated strings from caller (Recommended)

Add optional parameters `greeting_title: str | None = None` and `member_count_text: str | None = None` to `generate_greeting_card()`. The caller (`GreetingService`) resolves translations via `t()` and passes them in. If `None`, fall back to current English defaults for backwards compatibility.

- **Pros**: Clean separation of concerns — ImageService stays i18n-free; caller owns locale resolution; easy to test
- **Cons**: Slightly more parameters to thread through
- **Effort**: Low-Medium

### Approach C: Full card redesign with localization + visual overhaul

Redesign the card layout: add guild icon, accent color strip, bold font variant, timestamp, decorative border around avatar, distinct welcome vs. goodbye color themes. Add localization via Approach B. Add new font assets.

- **Pros**: Substantial UX improvement; addresses user's "welcome is a mierda" complaint holistically
- **Cons**: Larger scope; needs new font assets; more layout constants to maintain
- **Effort**: Medium-High

## Recommendation

**Approach B** as the foundation, with selective elements from Approach C for the UX/UI improvement.

**Why Approach B over A**: The `ImageService` should remain a pure synchronous Pillow renderer with no i18n dependency. This follows the project's architecture where services are testable without external dependencies. The caller already has access to `guild_id` and the `t()` function.

**Selective C elements**: Add a guild icon overlay and a subtle accent color bar to visually distinguish the card from a plain gradient. This addresses the user's stated dissatisfaction ("el welcome es una mierda") without a full redesign.

### Implementation sketch

1. **Add locale keys** to `es.json` and `en.json`:
   ```json
   "greetings": {
     "card": {
       "welcome_title": "¡Bienvenido",
       "goodbye_title": "¡Hasta luego",
       "member_count": "Miembro #{count}"
     }
   }
   ```

2. **Add `greeting_title` and `member_count_text` params** to `generate_greeting_card()`. If `None`, fall back to current English hardcoded strings.

3. **In `dispatch_welcome()` and `dispatch_goodbye()`**: resolve guild language from `_guild_languages` (already populated by `GuildService`), call `t(guild_id, "greetings.card.welcome_title")` and `t(guild_id, "greetings.card.member_count", count=member_count)`, pass results to `generate_greeting_card()`.

4. **In `welcome_test` and `goodbye_test` commands**: same pattern — resolve `t()` and pass localized strings.

5. **Visual enhancement**: Add guild icon (if available) as a small overlay in the top-right corner. Optionally add a thin accent color bar at the bottom.

6. **Tests**: Add parametrized tests verifying that Spanish and English guilds produce cards with the correct localized text (by checking the text parameters passed to the mock, not the Pillow rendering).

## Risks

- **Font glyph coverage**: The existing `Inter-Regular.ttf` font may not support all characters in translated strings (accented characters are fine; CJK would be an issue). Currently only `es` and `en` are supported, so this is not an immediate concern.
- **Backwards compatibility**: Existing tests mock `generate_greeting_card` and assert on its call signature. Adding optional params is backwards-compatible but tests should be updated to verify the new params are passed correctly.
- **Template placeholders**: The `{count}` placeholder in the new locale key must not collide with the existing `_format_template()` placeholders (`{mention}`, `{user}`, `{server}`). Using a distinct name (`{count}`) avoids this.

## Ready for Proposal

**Yes.** The root cause is clearly identified (hardcoded English in `image_service.py` lines 303/319), the fix path is well-defined (Approach B), Supabase data confirms the guild is configured for Spanish, and the affected files and test boundaries are mapped. The orchestrator should proceed to `sdd-propose` for `welcome-localization-ux`.
