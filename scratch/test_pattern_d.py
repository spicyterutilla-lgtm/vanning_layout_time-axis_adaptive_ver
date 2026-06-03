import sys
import datetime
sys.path.append('.')
from data_loader import DataLoader
from vanning_engine import VanningEngine
from services.validation import classify_items_for_day

loader = DataLoader()
items = loader.load_from_excel('simulationdata/D_case_master_based_simulation_data.xlsx', sheet_name='シミュレーションデータ')
print('Total loaded items:', len(items))

# same logic as optimize.py
current_date = datetime.date(2026, 6, 25) - datetime.timedelta(days=7) # vanning start date = 6/18 for test
day_groups = classify_items_for_day(items, datetime.date(2026, 6, 25), 21)
target_items = day_groups['must_ship']
print('Must ship:', len(target_items))

engine = VanningEngine(vanning_base_date=datetime.date(2026, 6, 25))
containers, unpacked = engine._run_basic_packing_once(target_items)
print('Packed items:', sum(len(c.items) for c in containers))
print('Unpacked items:', len(unpacked))

if unpacked:
    for u in unpacked[:10]:
        print(f"Unpacked item: {u.id}, status: {getattr(u, 'status_msg', 'none')}, weight: {u.weight}, creation: {u.creation_date}, exp: {u.expiration_date}")
