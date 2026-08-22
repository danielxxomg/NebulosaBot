# Voice Observatory Specification

## Purpose

Provide a read-only voice state observatory: enable the Voice States intent, listen to `on_voice_state_update`, classify transitions (join/leave/move/mute/deafen), and route guild-scoped log embeds to the configured log channel via `LoggingService.log_voice_event`. The listener MUST NOT kick, mute, move, DM, or send into voice channels — it observes and logs only.

## Requirements

### Requirement: Intent flag is enabled

The system MUST enable `intents.voice_states` in `bot/__main__.py` so the bot receives `on_voice_state_update` events. The change MUST document in `bot/__main__.py` and `docs/MANUAL.md` that the guild owner MUST enable the Voice States intent in the Discord Developer Portal (the bot cannot detect a missing grant).

#### Scenario: Intent flag is enabled

- GIVEN `bot/__main__.py` after the change
- WHEN the bot constructs its intents
- THEN `intents.voice_states` is `True`

#### Scenario: Portal toggle documented

- GIVEN the `bot/__main__.py` and `docs/MANUAL.md` after the change
- WHEN a guild owner reads the documentation
- THEN they see a prerequisite instructing them to enable the Voice States intent in the Discord Developer Portal

### Requirement: Voice event routed to the correct guild's log channel

`LoggingService` MUST expose an `async def log_voice_event(guild_id, member, transition, before, after)` method that resolves the log channel via the `{guild_id}:config` cache (fallback DB), checks `_should_log` (`logEnabled` true AND `logChannelId` not null), and sends a formatted embed with `brand.LOG_COLOR` (INFO) to guild G's `logChannelId` only. When `logEnabled` is false or `logChannelId` is null, the method MUST skip silently (no embed, no error). The method MUST be async with `await` between DB/log ops (no blocking I/O).

#### Scenario: Guild-scoped and async-only

- GIVEN guild A and guild B have different `logChannelId` values
- WHEN a voice event fires in guild A
- THEN an embed is sent to guild A's `logChannelId` only (guild B is not touched)

#### Scenario: Voice event routed to the correct guild's log channel

- GIVEN a voice event fires in guild A with `logEnabled=true` and `logChannelId` set
- WHEN `log_voice_event` is called
- THEN the embed is sent to guild A's log channel

#### Scenario: Logging disabled skips silently

- GIVEN `logEnabled=False`
- WHEN `log_voice_event` is called
- THEN no embed is sent and no error is surfaced

#### Scenario: No log channel skips silently

- GIVEN `logEnabled=True` but `logChannelId` is null
- WHEN `log_voice_event` is called
- THEN no embed is sent and no error is surfaced

### Requirement: on_voice_state_update listener is read-only

The system MUST provide a `VoiceListener(commands.Cog)` in `bot/listeners/voice_listener.py` with a `@commands.Cog.listener() async def on_voice_state_update(member, before, after)`. The listener MUST skip bots and both-None events (no channel change). The listener MUST classify the transition: join (`before.channel=None`, `after` set), leave (`before` set, `after.channel=None`), move (both set, different channels), mute/deafen (`self_mute` or `self_deaf` changed). The listener MUST route the event via `LoggingService.log_voice_event`. The listener MUST be read-only: it MUST NOT kick, mute, move, DM the member, or send messages into a voice channel.

#### Scenario: Join logged

- GIVEN a non-bot member joins a voice channel (`before.channel=None`, `after` set)
- WHEN `on_voice_state_update` fires
- THEN a voice-join event is logged via `log_voice_event`

#### Scenario: Leave logged

- GIVEN a non-bot member leaves a voice channel (`before` set, `after.channel=None`)
- WHEN `on_voice_state_update` fires
- THEN a voice-leave event is logged

#### Scenario: Move logged

- GIVEN a non-bot member moves between two voice channels (both set, different)
- WHEN `on_voice_state_update` fires
- THEN a voice-move event is logged (from → to)

#### Scenario: Mute/deafen toggles logged

- GIVEN a non-bot member's `self_mute` or `self_deaf` toggles
- WHEN `on_voice_state_update` fires
- THEN a mute/deafen event is logged

#### Scenario: on_voice_state_update listener is read-only

- GIVEN the `VoiceListener` handles an event
- WHEN it routes the event
- THEN it does NOT kick, mute, move, DM the member, or send into a voice channel

### Requirement: Rapid toggles are debounced

The listener MUST maintain a per-member debounce dict keyed `f"{guild_id}:{member_id}"` with a TTL (e.g. 2.0 seconds). Rapid toggles within the debounce window MUST collapse to at most 1 log entry (not 5). The debounce MUST be guild-scoped: rapid toggles by a member in guild A MUST NOT affect guild B. The listener MUST evict stale debounce entries on every event (no unbounded growth).

#### Scenario: Rapid toggles are debounced

- GIVEN a member fires 5 `self_mute` toggles within the 2-second debounce window
- WHEN the events are processed
- THEN at most 1 log entry is emitted (not 5)

#### Scenario: Debounce is guild-scoped

- GIVEN guild A and guild B both have a member with the same `member_id`
- WHEN rapid toggles fire in guild A
- THEN guild B's debounce entry is unaffected and guild B can still log

#### Scenario: Stale debounce entries are evicted

- GIVEN the debounce dict contains entries older than the TTL
- WHEN the next `on_voice_state_update` fires
- THEN stale entries are evicted (no unbounded growth)
