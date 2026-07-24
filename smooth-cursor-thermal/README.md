# smooth-cursor-thermal

Stops the cursor (and the whole desktop) from stuttering when the machine runs
hot — most noticeable at low battery, when max-rate charging adds chassis heat
on top of CPU load and thermald throttles hardest.

**The cause:** when the CPU package nears its thermal limit, thermald escalates
to the `intel_powerclamp` cooling device, which injects synchronized forced-idle
cycles across *all* cores (observed at 49% duty on the MacBookPro11,4). The
compositor freezes in lockstep and the cursor visibly stutters.

**The fix:** blacklist `intel_powerclamp`. thermald then throttles purely by
frequency capping (RAPL / intel_pstate / cpufreq), which slows work down but
never freezes all cores at once — the cursor stays smooth even at high temps.

**Safety:** unchanged. thermald still caps frequency (down to 800 MHz if
needed), and the CPU's own hardware PROCHOT throttling at 100°C is the final
backstop regardless of any software.

## Install

```bash
sudo install -Dm644 blacklist-powerclamp.conf /etc/modprobe.d/blacklist-powerclamp.conf
sudo systemctl restart thermald
sudo modprobe -r intel_powerclamp
```

## Verify

```bash
lsmod | grep powerclamp          # should print nothing
grep -l powerclamp /sys/class/thermal/cooling_device*/type  # nothing
```

On the MacBookPro11,4 this dropped the package temp from 96°C to 88°C within
seconds (frequency capping is also simply more efficient than idle injection)
while the cursor went back to full smoothness under an all-core load.
