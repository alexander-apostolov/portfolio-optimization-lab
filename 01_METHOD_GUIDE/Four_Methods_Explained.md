# Four Methods Explained

## MSA — Multi-Step Allocation
A stepwise ranking and repair method that constructs a portfolio through manageable allocation stages, then checks and repairs against structural, budget, and constraint feasibility rules.

## Standard Octane
A ranking-family method based on portfolio value density and constraint economics. It uses the Standard Octane ranking and pre-repair selection, then applies POL structural and feasibility logic.

## Adjusted Octane (aOctane) — current working definition
Adjusted Octane starts from the Standard Octane ranking and pre-repair selection; the final selection may differ only through POL's standard structural repair. After repair and feasibility validation, aOctane applies a bounded local sequencing and re-timing improvement pass, guarded so that the validated aOctane result cannot underperform the corresponding validated Octane baseline.

## sCPA-lite
A bounded stochastic combination-permutation approximation. It searches more broadly across configurations and sequences than ranking-family methods, but it is not exhaustive and must not be presented as proof of global optimality.
