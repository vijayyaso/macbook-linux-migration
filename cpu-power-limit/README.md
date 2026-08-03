# cpu-power-limit

Undervolts the CPU by 50 mV and caps the sustained package power (PL1) at
**37W instead of the stock 45W**, so the machine stops hitting its thermal
limit under load.

**The cause:** the MacBookPro11,4 ships a 47W-TDP Crystal Well Haswell in a
cooler that cannot actually dissipate 45W sustained. At the stock limit an
all-core load rides 92–100°C with *both fans already pegged at maximum*,
repeatedly touching TjMax (100°C). The hardware then throttles hard — and on
this machine those throttle events are what stall `i915` page flips, which is
the desktop lag and cursor stutter you feel. See also
[`smooth-cursor-thermal/`](../smooth-cursor-thermal/), which fixes the other
half of that problem.

**The fix:** lower PL1 to 37W. The CPU settles below the throttle point and
simply never gets there.

**This is not a paste or mount problem.** Worth stating plainly, because the
obvious reaction is to repaste. On this machine, measured after a fresh
repaste *and* a fin-stack clean:

- core-to-core spread under full load was 4°C (91/91/91/87) — an uneven
  heatsink mount shows 10–15°C, so contact was fine;
- the repaste changed the sustained temperature by nothing at all, because
  heat transfer to the heatsink was never the bottleneck.

The limit is how much heat the fins and fans can move out of the chassis.
Repasting cannot raise that. Lowering the power the CPU is allowed to draw is
the only lever that works.

## Measured

5-minute all-core burn, `turbostat` sampling every 10s, ambient ~25°C:

| | PL1 45W (stock) | PL1 37W |
|---|---|---|
| Sustained all-core clock | ~3.0–3.2 GHz | 2894 MHz |
| Package temperature | 92–100°C, oscillating | **82–83°C, flat** |
| TjMax (100°C) hits | yes | none |
| Time thermally throttled | 22.9s / 18,952 events | none |
| Fans | 6156 / 5700 RPM (pegged) | 6075 / 5628 RPM |

The ~200 MHz gap is smaller in practice than it looks: the 45W figure is
throttle-inflated. That run dipped as low as 1596 MHz whenever it touched
TjMax and spent 22.9 seconds clamped, while the 37W run never throttled once.
Sustained throughput is close to a wash, and far more consistent — you trade a
little peak clock for the elimination of the stalls.

For reference, the CPU's base clock is 2.2 GHz, so 2894 MHz sustained on all
four cores is still comfortably above spec.

## Install

Requires `intel-undervolt` (Ubuntu/Zorin: `sudo apt install intel-undervolt`).

```bash
sudo install -Dm644 intel-undervolt.conf /etc/intel-undervolt.conf
sudo install -Dm644 thermal-cpu-cdev-order.xml /etc/thermald/thermal-cpu-cdev-order.xml

sudo systemctl enable --now intel-undervolt.service intel-undervolt-loop.service
sudo systemctl restart thermald
```

Back up whatever was there first if you have existing settings — the package
ships its own `/etc/intel-undervolt.conf`.

The `thermal-cpu-cdev-order.xml` half is **not optional**. Without it thermald
keeps `rapl_controller` in its cooling-device order and resets PL1 back to the
firmware default of 100W as soon as temperatures drop, silently undoing the
cap within seconds.

## Verify

```bash
sudo intel-undervolt read
```

Expect `-49.80 mV` on CPU and CPU Cache, and:

```
Short term package power: 60 W, 0.002 s, enabled
Long term package power: 37 W, 28.000 s, enabled
```

Confirm the kernel agrees, and that thermald is not fighting it:

```bash
cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw   # 37000000
grep -l rapl /sys/class/thermal/cooling_device*/type               # nothing
```

Then load all cores for a couple of minutes and watch it hold:

```bash
for i in $(seq $(nproc)); do (while :; do :; done) & done
watch -n2 'sensors | grep -E "Package id|side"'
# kill %1 %2 ... when done, or: pkill -f "while :"
```

Package temperature should stabilise in the low 80s and stay there.

## Persistence

- **Reboot** — `intel-undervolt.service` applies at boot, `intel-undervolt-loop.service`
  keeps the values in place while running.
- **Suspend/resume** — `/lib/systemd/system-sleep/intel-undervolt`, shipped with the
  package, re-reads this same config on resume. Nothing extra needed; the MSRs
  are otherwise lost across S3.

## Tuning

37W is the setting that made this specific chassis stop throttling. Adjust the
long-term value in `intel-undervolt.conf` and re-run the burn above:

- higher (40–42W) — a little more clock, back toward the low 90s°C;
- lower (32–35W) — cooler and quieter still, noticeably less sustained clock.

Only the long-term (PL1) number matters for sustained load. Leave PL2 at 60W;
short bursts are what makes the machine feel fast, and the heatsink absorbs
them without complaint.

## Revert

```bash
sudo apt install --reinstall intel-undervolt   # restores the stock config
sudo rm /etc/thermald/thermal-cpu-cdev-order.xml
sudo systemctl restart thermald
sudo reboot
```
