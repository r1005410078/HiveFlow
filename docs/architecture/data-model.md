# HiveFlow Data Model (V1 Foundation)

This document describes the first-pass domain model boundaries.

## Core Entities

- `Strategy`
  Stores strategy definition and baseline context.
- `StrategySlot`
  Represents capital-purpose slots (`attack`, `defense`, `long-term`).
- `Position`
  Represents actual holdings state.
- `RiskSignal`
  Represents per-symbol risk waterline and score.
- `TargetAllocation`
  Represents strategy-generated target weights.
- `AssetMix`
  Represents account-level capital mix across slots.
- `RebalanceSuggestion`
  Represents generated action proposals from actual-vs-target deltas.
- `DecisionLog`
  Stores user-confirmed decisions and corrections.
- `UserPreference`
  Stores persistent preference keys and values.

## Relationship Summary

- `Strategy` drives `TargetAllocation`.
- `Position` is compared against `TargetAllocation`.
- `RiskSignal` and `AssetMix` influence `RebalanceSuggestion` priority.
- `DecisionLog` and `UserPreference` preserve long-term context.
