"""Build every BCM entity this fork adds and print the state it would report.

Polls the device when it is reachable and falls back to a recorded dump, then
runs the same values through synthetic variations. Home Assistant is replaced
by `hastub`, so this needs nothing but the standard library:

    python3 tools/verify_bcm_entities.py <device ip>
"""
import sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import hastub; hastub.install()
sys.path.insert(0, str(REPO))

import importlib.util
spec = importlib.util.spec_from_file_location("poller", HERE / "sihas_poll.py")
poller = importlib.util.module_from_spec(spec); spec.loader.exec_module(poller)

from custom_components.sihas import bcm, sensor, number

# Captured from 172.30.1.51 on 2026-11-03 13:44 KST (boiler idle).
RECORDED = [
    1, 19, 60, 0, 3, 0, 0, 520,
    206, 20, 0, 0, 0, 0, 0, 3,
    43, 0, 30, 0, 8, 2, 0, 40,
    5, 85, 40, 4800, 1205, 1, 0, 0,
] + [0] * 21 + [2, 0, 0, 0, 0, 0, 0, 0, 27, 0, 21344]
assert len(RECORDED) == 64

ip = sys.argv[1]
resp = poller.send(poller.poll_pkt(), ip)
if resp is not None and len(resp) == 137:
    registers = poller.regs(resp)
    print(f"source: live poll of {ip}")
else:
    registers = RECORDED
    print("source: recorded dump (device unreachable)")
state = bcm.BcmState(tuple(registers))

class FakeCoordinator:
    data = state
    entry = type("E", (), {"data": {"mac": "aa:bb:cc:dd:ee:ff", "ip": ip, "name": "보일러"}})()
    hot_water_kind = state.hot_water_kind
    def temperature_limits(self, s, mode):
        return s.limits(mode)

c = FakeCoordinator()

print(f"raw: r7={registers[7]} r9={registers[9]} r10={registers[10]} "
      f"r11={registers[11]} r12={registers[12]} r13={registers[13]} r14={registers[14]}")
print(f"timer_cycle={state.timer_cycle}")
print()

entities = [
    sensor.BcmOndolTemperature(c),
    sensor.BcmHotWaterTemperature(c),
    sensor.BcmBurning(c),
    sensor.BcmErrorCode(c),
    sensor.BcmWaterStatus(c),
    sensor.BcmConnectivity(c),
    number.BcmTimerCycle(c, "timer_interval", 0, "h"),
    number.BcmTimerCycle(c, "timer_runtime", 1, "min"),
]
for e in entities:
    value = e.native_value
    extra = ""
    if isinstance(e, number.BcmTimerCycle):
        extra = (f"  range={e._attr_native_min_value}..{e._attr_native_max_value}"
                 f" {e._attr_native_unit_of_measurement}")
    options = getattr(e, "_attr_options", None)
    if options is not None:
        assert value in options, f"{e._attr_unique_id}: {value!r} not in {options}"
        extra = f"  options={options}"
    print(f"{e._attr_unique_id:<45} translation={e._attr_translation_key:<38} "
          f"value={value!r}{extra}")

ws = sensor.BcmWaterStatus(c)
print("\nwater_status attributes:", ws.extra_state_attributes)

# Exercise the R7 write path without touching the device.
import asyncio
written = []
async def fake_command(resolve):
    written.append(resolve(c.data))
c.async_set_timer_cycle = bcm.BcmCoordinator.async_set_timer_cycle.__get__(c, FakeCoordinator)
c._async_command = fake_command
asyncio.run(c.async_set_timer_cycle(interval=12))
asyncio.run(c.async_set_timer_cycle(runtime=35))
asyncio.run(c.async_set_timer_cycle(interval=3, runtime=5))
print("\nR7 writes (register, value):", [(int(r), v) for r, v in written])

from homeassistant.exceptions import ServiceValidationError
for bad in ({"interval": 0}, {"interval": 25}, {"runtime": 60}, {"runtime": -1}):
    try:
        asyncio.run(c.async_set_timer_cycle(**bad))
    except ServiceValidationError as err:
        print(f"rejected {bad}: {err}")
    else:
        raise AssertionError(f"{bad} was accepted")


print("\n--- synthetic states ---")
def variant(overrides):
    regs = list(registers)
    for index, value in overrides.items():
        regs[index] = value
    return bcm.BcmState(tuple(regs))

for label, overrides in (
    ("burning, hot water 48C, ondol 71C", {11: 1, 10: 48, 9: 71}),
    ("water refill needed", {13: 1}),
    ("undocumented water value 2", {13: 2}),
    ("water value 9 (out of range)", {13: 9}),
    ("boiler offline + error 32", {14: 1, 12: 32}),
    ("R7 unreadable (9999)", {7: 9999}),
    ("R7 = 1210", {7: 1210}),
):
    c.data = variant(overrides)
    parts = []
    for e in entities:
        value = e.native_value
        options = getattr(e, "_attr_options", None)
        if options is not None and value is not None:
            assert value in options, f"{e._attr_unique_id}: {value!r} not in {options}"
        parts.append(f"{e._attr_translation_key.removeprefix('bcm_')}={value}")
    print(f"{label:<36} " + "  ".join(parts))

c.data = variant({7: 9999})
try:
    asyncio.run(c.async_set_timer_cycle(interval=6))
except ServiceValidationError as err:
    print(f"\nrejected partial write on unreadable R7: {err}")
else:
    raise AssertionError("partial write on unreadable R7 was accepted")
written.clear()
asyncio.run(c.async_set_timer_cycle(interval=6, runtime=30))
print("full write on unreadable R7:", [(int(r), v) for r, v in written])
