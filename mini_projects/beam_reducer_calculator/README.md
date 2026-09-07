# Beam Reducer Lens Calculator

Standalone browser calculator for a two-positive-lens Keplerian beam reducer.

## Use

Open `index.html` directly in a browser. No installation or server is required.

Inputs:
- input beam diameter `D_in` in mm
- target output beam diameter `D_out` in mm
- known first/input-side lens focal length `f1` in mm

Outputs:
- magnification `M = D_out / D_in`
- required second-lens focal length `f2 = f1 * M`
- reduction factor `D_in / D_out`
- nominal lens spacing `f1 + f2`

## Assumptions

- thin lenses
- paraxial approximation
- collimated input and output beams
- positive-positive Keplerian telescope
- `f1` is the first/input-side lens focal length

The calculated spacing is a nominal thin-lens value. In a real optical setup, fine adjustment may be required because of lens thickness, principal-plane location, residual beam divergence, aberrations, and beam quality.

## Reference checks

- `D_in = 17 mm`, `D_out = 3 mm`, `f1 = 398 mm` → `f2 ≈ 70.24 mm`, spacing `≈ 468.24 mm`
- `D_in = 17 mm`, `D_out = 2.5 mm`, `f1 = 398 mm` → `f2 ≈ 58.53 mm`, spacing `≈ 456.53 mm`

The page runs these two reference checks in the browser and reports whether they pass.
