# Portfolio Optimization Lab (POL)

A simulation engine for project portfolio optimization. Simultaneous selection and scheduling under resource constraints and time-dependent profit erosion. This framework supports the benchmarking and evaluation of four allocation methods, featuring the heuristic Stochastic Combination-Permutation Algorithm (**sCPA-lite**).

---

## 🎯 Purpose of this Repository & Research Context

This simulation engine is the exact computational tool used to generate the empirical results and benchmarks presented in the article:
* **Article 3 (Validation):** *A Single Comparative Measure for Decision Support in Project and Portfolio Management* (PM World Journal, Vol. XV, Issue VII – July 2026).

This research is the direct culmination of a framework established across two foundational papers:
1. **Article 1 (The Core Theory):** *The Combination-Permutation Algorithm: Optimizing Portfolio Allocation with TOC and Cost of Time* (PM World Journal, Vol. XIV, Issue VII – July 2025) – which introduced the mathematical integration of the Theory of Constraints with time-dependent profit erosion.
2. **Article 2 (Advancing the CPA):** *Advancing the Combination-Permutation Algorithm* (PM World Journal, Vol. XV, Issue II – February 2026) – which advanced the foundational algorithm and detailed the underlying framework.

### Why this Code is Now Public (Call for Collaboration)
We have made this core engine and the 10 reference "Lab Worlds" fully open-source to establish a transparent, verifiable benchmark for the project and portfolio management communities. 

**We invite scientists, developers, and enterprise software architects to join this project.** We are seeking collaboration to:
* **Improve the core heuristics:** Optimize the iteration loops to achieve faster convergence on large portfolios.
* **Develop integrations:** Build open-source API adapters to connect this simulation engine with project and portfolio management (incl. AI-PMO) tools.
* **Expand the model:** Test and refine the engine against multi-candidate or dynamic "wandering" constraints in diverse industry setups.
