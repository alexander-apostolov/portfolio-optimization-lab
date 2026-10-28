# Portfolio Waste Metrics

Waste is the economic value left unrealized because a method selected, sequenced, or staged a weaker portfolio than the best validated comparator in the same world.

```text
Best Profit_w = max(P85 profit among admissible comparable methods in world w)
Absolute Waste_method,w = Best Profit_w - Method Profit_method,w
Percent Waste_method,w = Absolute Waste_method,w / Best Profit_w * 100
```

Rules: compute waste per world before aggregation; if Best Profit <= 0, percent waste is denominator-unsafe; negative method profit can create waste above 100%; inadmissible methods are not best comparators; sCPA-lite has zero waste only where it is best validated comparator.

Report ROI on used budget, active budget envelope, and full planning-horizon budget envelope. Treat unused budget as management reserve when appropriate.
