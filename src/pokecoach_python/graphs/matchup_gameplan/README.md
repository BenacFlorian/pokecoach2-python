# Description
This graph produces the Phase E matchup synthesis from already prepared Phase D sources. It loads the persisted source bundle for one run, checks its hash, then performs one structured LLM call to generate the final gameplan and win condition.

# Operation / Flow
1. `load_sources`
   Loads `execution_metadata.synthesis.sources` for the target run and verifies that the stored hash matches the invocation input.
2. `generate_gameplan`
   Builds the local `HumanMessage`, calls the DeepInfra-backed structured client once, then validates business references against the loaded sources.
3. `END`
   Returns the validated `StrategyOutput`.

# Input
- `run_id`
- `sources_hash`
- `execution_id`

# Output
- `StrategyOutput`
  - `gameplan`
  - `winCondition`
