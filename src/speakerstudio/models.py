"""User-facing device state; hardware identifiers are never inferred from artwork."""
from dataclasses import dataclass, field

LEGACY_MODELS = {'TITUS': 'megaboom', 'MAXIMUS': 'boom-2', 'MENDOCINO': 'boom-3',
                 'HUMBOLDT': 'megaboom-3', 'BOOM': 'boom'}
ARTWORK_MODELS = ('megaboom-3', 'boom-3', 'megaboom-4', 'boom-4', 'everboom', 'epicboom', 'hyperboom', 'wonderboom-4')


@dataclass
class Speaker:
    address: str
    path: str
    name: str
    model: str = ''
    identity: str = ''
    paired: bool = False
    connected: bool = False
    busy: bool = False
    battery: int | None = None
    volume: int | None = None
    volume_steps: int = 31
    eq: int | None = None
    firmware: str = ''
    error: str = ''
    colour: str = ''
    features: dict = field(default_factory=dict)
    members: list = field(default_factory=list)
    bands: list | None = None
    broadcast: int = 0
    member_info: dict = field(default_factory=dict)

    @property
    def title(self):
        return self.model.upper().replace('-', ' ') if self.model else 'Ultimate Ears speaker'
