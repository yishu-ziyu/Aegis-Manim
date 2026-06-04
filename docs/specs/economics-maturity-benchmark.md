# Aegis Economics Maturity Benchmark

This benchmark checks whether Aegis can turn advanced Chinese economics reasoning into a staged Manim animation, not just convert formulas into generic charts.

## Case: Slutsky and Hicks Decomposition

Prompt category: Chinese graduate-level microeconomics.

Core task:

- Derive Marshallian demand for `U(x,y)=(sqrt(x)+sqrt(y))^2` with `p_y=1`, `p_x=p`, and `m=12`.
- Animate the price change from `p=1` to `p=4`.
- Show initial and final budget lines, indifference curves, and optima.
- Show Slutsky compensation and Hicks compensation as two distinct concepts.
- Explain in Chinese why the Slutsky line passes through the original bundle while the Hicks line is tangent to the original indifference curve.

## Expected Economics

Marshallian demand:

```text
x(p,m) = m / (p(1+p))
y(p,m) = mp / (1+p)
```

Initial optimum:

```text
p0 = 1, m = 12
A = (6, 6)
U0 = 24
```

Final optimum:

```text
p1 = 4, m = 12
C = (0.6, 9.6)
U1 = 15
Total effect on x = -5.4
```

Slutsky compensation:

```text
mS = 4 * 6 + 6 = 30
S = (1.5, 24)
Substitution effect on x = -4.5
Income effect on x = -0.9
```

Hicks compensation:

```text
e(4, 24) = 19.2
H = (0.96, 15.36)
Substitution effect on x = -5.04
Income effect on x = -0.36
```

## Required Animation Objects

The generated animation should include:

- Initial budget line `y=12-x`, with intercepts.
- Final budget line `y=12-4x`, shown as an inward rotation around the y-axis intercept.
- Initial optimum `A=(6,6)` as the tangency between the initial budget line and initial indifference curve.
- Final optimum `C=(0.6,9.6)`.
- Indifference curves generated from `U=(sqrt(x)+sqrt(y))^2`, not arbitrary convex curves.
- Slutsky compensation line `y=30-4x`, visibly passing through `A=(6,6)`.
- Hicks compensation line `y=19.2-4x`, visibly tangent to the original indifference curve.
- Effect arrows for `x0=6 -> xS=1.5 -> x1=0.6`.
- Effect arrows for `x0=6 -> xH=0.96 -> x1=0.6`.
- Chinese narration distinguishing `买得起原消费束` from `保持原效用水平`.

## Repository Review Criteria

A generated work can enter the candidate repository only if it has:

- A completed render job with a project-owned Supabase video URL.
- The original prompt, generated code, scene name, and video URL.
- Review metadata with `review_stage=candidate` and `review_status=pending`.

A work can be promoted to the public community layer only after review confirms:

- The economic derivation is materially correct.
- The animation contains the required visual objects.
- Slutsky and Hicks compensation are not confused.
- Chinese labels and narration render without mojibake.

