"""BCM temperature set points and reservation cycle, independent of power and mode."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bcm import (
    HOT_WATER,
    ONDOL,
    ROOM,
    TARGET_REGISTERS,
    TIMER_INTERVAL_RANGE,
    TIMER_RUNTIME_RANGE,
    BcmCoordinator,
    BcmEntity,
    get_coordinator,
)
from .const import CONF_TYPE

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data[CONF_TYPE] != "BCM":
        return
    coordinator = get_coordinator(hass, entry)
    entities = [
        BcmTemperature(coordinator, "room_temperature", ROOM),
        BcmTemperature(coordinator, "ondol_temperature", ONDOL),
    ]
    if coordinator.hot_water_kind == "linear":
        entities.append(BcmTemperature(coordinator, "hot_water_temperature", HOT_WATER))
    entities += [
        BcmTimerCycle(coordinator, "timer_interval", 0, UnitOfTime.HOURS),
        BcmTimerCycle(coordinator, "timer_runtime", 1, UnitOfTime.MINUTES),
    ]
    async_add_entities(entities)


class BcmTemperature(BcmEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: BcmCoordinator, key: str, mode: str) -> None:
        super().__init__(coordinator, key)
        self.mode_name = mode

    @property
    def available(self) -> bool:
        return super().available and self._limits is not None

    @property
    def _limits(self) -> tuple[int, int] | None:
        return self.coordinator.temperature_limits(
            self.coordinator.data, self.mode_name
        )

    @property
    def native_min_value(self) -> float:
        return self._limits[0] if self._limits else 0

    @property
    def native_max_value(self) -> float:
        return self._limits[1] if self._limits else 0

    @property
    def native_value(self) -> float:
        return self.coordinator.data[TARGET_REGISTERS[self.mode_name]]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_temperature(value, self.mode_name)


class BcmTimerCycle(BcmEntity, NumberEntity):
    """One half of R7, which packs the reservation cycle as HHMM."""

    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(
        self, coordinator: BcmCoordinator, key: str, part: int, unit: str
    ) -> None:
        super().__init__(coordinator, key)
        self._part = part
        self._attr_native_unit_of_measurement = unit
        low, high = TIMER_INTERVAL_RANGE if part == 0 else TIMER_RUNTIME_RANGE
        self._attr_native_min_value = low
        self._attr_native_max_value = high

    @property
    def native_value(self) -> float | None:
        cycle = self.coordinator.data.timer_cycle
        return None if cycle is None else cycle[self._part]

    async def async_set_native_value(self, value: float) -> None:
        if self._part == 0:
            await self.coordinator.async_set_timer_cycle(interval=int(value))
        else:
            await self.coordinator.async_set_timer_cycle(runtime=int(value))
