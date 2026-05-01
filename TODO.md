# TODO

## Phase 1 - MVP Pipeline

- [x] Config + env validation
- [x] Telegram parser (Pyrogram userbot)
- [x] Regex prefilter for candidate leads
- [x] AMQP publish/consume helpers
- [x] LLM verification worker (OpenRouter)
- [x] Webhook notification to CF Worker
- [x] Optional save to Supabase

## Phase 2 - Reliability

- [ ] Deduplication by source/chat/message
- [ ] Retry policy + dead-letter queue for failed messages
- [ ] Healthcheck and startup self-test
- [ ] Structured logging with correlation_id

## Phase 3 - Quality

- [ ] Unit tests for prefilter patterns
- [ ] Unit tests for payload mapping
- [ ] Integration test: parser -> queue -> worker
- [ ] False-positive tuning based on real chat data

## Phase 4 - Productization

- [ ] Admin command to adjust keyword/pattern list
- [ ] Per-chat scoring thresholds
- [ ] Daily analytics in Supabase (leads/day, precision)
- [ ] Docker compose for local run
