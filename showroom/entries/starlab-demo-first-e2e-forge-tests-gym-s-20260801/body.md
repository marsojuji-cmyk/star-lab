# starlab-demo first e2e: forge tests + gym smoke

Token-routed short mode; forge unittest OK; gym smoke 3/3 on dolphin3

- **kind:** experiment
- **project:** starlab-demo
- **source:** manual
- **captured:** 2026-08-01T06:39:44Z

## Paths

- `<projects-dir>/starlab-demo`
- `<projects-dir>/starlab-demo/hello.py`

## Proof

```bash
lab forge run --exp starlab-demo (exit 0)
lab gym smoke 3/3 PASS
audit 7578a2e61eaa quality=0.92
```
