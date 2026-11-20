"""Small, auditable configuration objects used by the simulator."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    region: str
    on_demand_rate: float
    committed_rate: float
    quota: int

    @property
    def discount_percent(self) -> float:
        return round((1 - self.committed_rate / self.on_demand_rate) * 100, 1)


DEFAULT_PROVIDERS = (
    Provider("AWS", "us-east-1", 0.120, 0.072, 42),
    Provider("Azure", "central-india", 0.130, 0.078, 36),
    Provider("GCP", "asia-south1", 0.110, 0.070, 40),
)

RISK_PROFILES = {
    "aggressive": {"quantile": 0.50, "ladder_share": 0.90, "label": "Lowest cost / highest exposure"},
    "balanced": {"quantile": 0.70, "ladder_share": 0.70, "label": "Recommended trade-off"},
    "conservative": {"quantile": 0.90, "ladder_share": 0.45, "label": "Highest protection / highest cost"},
}

