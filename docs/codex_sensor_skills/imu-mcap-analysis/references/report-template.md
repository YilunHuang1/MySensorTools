# IMU MCAP Fault Report Template

## Summary

- MCAP:
- Fault time:
- Fault:
- Direct trigger topic:
- Root-cause class:

## Topic Path

```text
<sensor> -> <publisher> -> <topic> -> <consumer callback> -> <internal conversion>
```

## Fault Sample

```text
topic:
log_time:
header_time:
acc:
acc_norm:
gyr:
```

## Statistics

```text
<topic> samples=<n> bad_count=<n> min=<v> p50=<v> p99=<v> max=<v>
```

## Interpretation

State whether the anomaly is present in the MCAP topic before conversion. Separate physical motion, sensor saturation, raw read glitches, and downstream conversion issues.

## Next Checks

List concrete source-side logs, code checks, and validation commands.
