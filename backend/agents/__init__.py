"""The five roles on the Campus Customs team. Each module declares one agent's spec."""

from agents.accounting import SPEC as ACCOUNTING
from agents.boss import SPEC as BOSS
from agents.customer_service import SPEC as CUSTOMER_SERVICE
from agents.facilities import SPEC as FACILITIES
from agents.inventory import SPEC as INVENTORY

SPECS = {s.name: s for s in (BOSS, INVENTORY, ACCOUNTING, FACILITIES, CUSTOMER_SERVICE)}
