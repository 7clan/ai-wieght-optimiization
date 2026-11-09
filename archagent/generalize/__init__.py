"""SESSION 037 — the generalization engine.

Modules:
  taskir          TaskIR: validated intermediate representation + dependency
                  graph + piece decomposition (Phase 2)
  prompting       Prompt builders enforcing the Phase-1 lessons
                  (anchor-inside-construct, demo-completeness, early-EOS
                  retry, near-miss detection)          (Phase 2)
  policy          Budget-aware conservative strategy policy (Phase 3)
  principles      Reusable reasoning-principle engine (Phase 4)
  promptevol      Reflective prompt evolution, small Pareto set (Phase 5)
  probe           Behavioral probes: reference oracles + bun route
                  probes + counterexample extraction (Phase 6)
  controller      The generation/repair loop wiring everything (Phase 3+)
"""
